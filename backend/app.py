import xmlrpc.client
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os
import shutil
import base64
import json
from datetime import datetime
from collections import deque
import threading
import time
import secrets

app = Flask(__name__)
CORS(app)

# Configuration
# Security: Load API Key from env or generate a random one
API_KEY = os.environ.get('CLOUDLEECHER_API_KEY')
if not API_KEY:
    API_KEY = secrets.token_hex(16)
    # Log to console (which might be redirected)
    print(f"WARNING: No API Key provided. Generated: {API_KEY}")

# Download paths
DOWNLOAD_DIR = "/content/temp_downloads"  # Local temporary storage
DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads" # Final destination in Drive
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# Ensure directories exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(DRIVE_DIR, exist_ok=True)

# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)

# Connect to Aria2 RPC
s = xmlrpc.client.ServerProxy(ARIA2_RPC_URL)

# History of tasks moved to Drive
history_log = deque(maxlen=50)
processed_gids = set()

def log(level, operation, message, gid=None, extra=None):
    """Add entry to log with timestamp and details"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,  # info, warning, error
        "operation": operation,
        "message": message,
        "gid": gid,
        "extra": extra
    }
    logs.append(entry)
    
    # Also write to file for persistence
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except:
        pass  # Don't crash on log write failure
    
    # Print to console for Colab visibility
    print(f"[{level.upper()}] {operation}: {message}" + (f" (GID: {gid})" if gid else ""))

# --- Authentication Middleware ---
@app.before_request
def check_auth():
    if request.method == 'OPTIONS':
        return
    if request.path == '/health': # Allow health check without auth
        return

    client_key = request.headers.get('x-api-key')
    if client_key != API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

# --- Background Monitor ---
class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

    def run(self):
        while self.running:
            try:
                self.check_and_move_completed()
            except Exception as e:
                print(f"Monitor Error: {e}")
            time.sleep(5)

    def check_and_move_completed(self):
        try:
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength", "completedLength", "infoHash"])
            for task in stopped:
                if task['status'] == 'complete' and task['gid'] not in processed_gids:
                    self.move_to_drive(task)
        except Exception as e:
            pass

    def move_to_drive(self, task):
        gid = task['gid']
        files = task.get('files', [])
        if not files:
            return

        # Determine the root file/folder name
        # Aria2 returns absolute paths. We need to find the file relative to DOWNLOAD_DIR
        # Usually the first file's path starts with DOWNLOAD_DIR

        # Simple heuristic: Move the top-level item (file or directory)
        # Check if it's a multi-file torrent
        first_file_path = files[0]['path']
        if not first_file_path.startswith(DOWNLOAD_DIR):
            # Something is wrong, maybe path configuration issue
            return

        # Rel path
        rel_path = os.path.relpath(first_file_path, DOWNLOAD_DIR)
        top_level_name = rel_path.split(os.sep)[0]

        source_path = os.path.join(DOWNLOAD_DIR, top_level_name)

        # Safety check: Prevent zombie loops if source is missing
        if not os.path.exists(source_path):
            log("warning", "move_to_drive", f"Source not found: {source_path}. Assuming already moved or deleted.", gid=gid)
            try:
                s.aria2.removeDownloadResult(gid)
                processed_gids.add(gid)

                # Add to history as 'complete' (best effort)
                task_copy = task.copy()
                task_copy['status'] = 'complete'
                task_copy['drive_path'] = "Lost (Source missing)"
                history_log.append(task_copy)
            except:
                pass
            return

        # Handle collision
        dest_path = os.path.join(DRIVE_DIR, top_level_name)
        if os.path.exists(dest_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            name, ext = os.path.splitext(top_level_name)
            if os.path.isdir(source_path):
                # Directory
                dest_path = os.path.join(DRIVE_DIR, f"{top_level_name}_{timestamp}")
            else:
                # File
                dest_path = os.path.join(DRIVE_DIR, f"{name}_{timestamp}{ext}")

        log("info", "move_to_drive", f"Moving {top_level_name} to Drive...", gid=gid)
        try:
            shutil.move(source_path, dest_path)
            log("info", "move_to_drive", f"Successfully moved to: {dest_path}", gid=gid)

            # Clean up aria2
            s.aria2.removeDownloadResult(gid)
            processed_gids.add(gid)

            # Add to history
            # Update task files path to point to Drive for display
            # We can't update all paths easily, but we can assume the task name remains
            task_copy = task.copy()
            task_copy['status'] = 'complete' # Ensure status is complete
            # We add a custom field to indicate it's safe on drive
            task_copy['drive_path'] = dest_path
            history_log.append(task_copy)

        except Exception as e:
            log("error", "move_to_drive", f"Move failed: {e}", gid=gid)

# Start monitor
monitor = BackgroundMonitor()
monitor.start()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "CloudLeecher-Backend"})

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Return recent backend logs for frontend inspection"""
    try:
        return jsonify({"logs": list(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/magnet', methods=['POST'])
def add_magnet():
    data = request.json
    magnet_link = data.get('magnet')
    if not magnet_link:
        log("error", "add_magnet", "Magnet link is required")
        return jsonify({"error": "Magnet link is required"}), 400
    
    # BACKEND QUEUE ENFORCEMENT: Only allow one active download
    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
    
    if len(active) > 0 or len(waiting) > 0:
        log("warning", "add_magnet", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
        return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
    
    try:
        # Enforce download dir option just in case
        options = {"dir": DOWNLOAD_DIR}
        gid = s.aria2.addUri([magnet_link], options)
        log("info", "add_magnet", "Magnet link added successfully", gid=gid, extra={"magnet": magnet_link[:50] + "..."})
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", f"Failed: {str(e)}", extra={"magnet": magnet_link[:50] + "..."})
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
def add_torrent_file():
    try:
        data = request.json
        b64_content = data.get('torrent')
        if not b64_content:
            log("error", "add_torrent_file", "Torrent file content is required")
            return jsonify({"error": "Torrent file content is required"}), 400

        # BACKEND QUEUE ENFORCEMENT: Only allow one active download
        active = s.aria2.tellActive(["gid", "status"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
        
        if len(active) > 0 or len(waiting) > 0:
            log("warning", "add_torrent_file", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
            return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        log("info", "add_torrent_file", f"Received torrent file ({len(raw_bytes)} bytes), adding to aria2...")
        # Enforce download dir
        options = {"dir": DOWNLOAD_DIR}
        gid = s.aria2.addTorrent(binary_torrent, [], options)
        log("info", "add_torrent_file", "Torrent file added successfully, downloading metadata...", gid=gid)
        
        # Try to get immediate status to log torrent info
        try:
            status = s.aria2.tellStatus(gid, ["gid", "status", "files", "bittorrent"])
            torrent_name = status.get('bittorrent', {}).get('info', {}).get('name', 'Unknown')
            log("info", "add_torrent_file", f"Torrent name: {torrent_name}", gid=gid, extra={"status": status.get('status')})
        except:
            pass
        
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent_file", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        # Use safe keys for non-active tasks to avoid API errors/empty responses
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(extended_keys)
        waiting = s.aria2.tellWaiting(0, 100, basic_keys)
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
        # Merge history into stopped
        # Convert history_log to list
        history_list = list(history_log)
        # Prepend to stopped so they show up? Or append?
        # Stopped from aria2 includes error/removed tasks that haven't been purged.
        # History includes successfully moved tasks.
        stopped.extend(history_list)

        # Track GID transitions for debugging
        all_tasks = active + waiting + stopped
        all_gids = [t['gid'] for t in all_tasks]
        
        # Check for GID relationships (followedBy/following)
        gid_transitions = []
        for task in all_tasks:
            if task.get('followedBy'):
                # This task created follow-up tasks
                for followed_gid in task['followedBy']:
                    gid_transitions.append(f"{task['gid'][:8]} → {followed_gid[:8]}")
                    log("info", "gid_transition", f"Task spawned follow-up", 
                        gid=task['gid'], 
                        extra={"followedBy": task['followedBy']})
            
            if task.get('following'):
                # This task is following another
                log("info", "gid_transition", f"Task is following {task['following']}", 
                    gid=task['gid'])
        
        if all_gids:
            # log_msg = f"Currently tracking {len(all_gids)} tasks"
            # if gid_transitions:
            #     log_msg += f" | Transitions: {', '.join(gid_transitions)}"
            # log("info", "status_poll", log_msg, extra={"gids": all_gids})
            # Reduced logging frequency to avoid spam
            pass
        
        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        log("error", "get_status", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
def pause_download():
    try:
        gid = request.json.get('gid')
        s.aria2.pause(gid)
        log("info", "pause_download", "Download paused", gid=gid)
        return jsonify({"status": "paused", "gid": gid})
    except Exception as e:
        log("error", "pause_download", f"Failed: {str(e)}", gid=request.json.get('gid'))
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
def resume_download():
    try:
        gid = request.json.get('gid')
        s.aria2.unpause(gid)
        log("info", "resume_download", "Download resumed", gid=gid)
        return jsonify({"status": "resumed", "gid": gid})
    except Exception as e:
        log("error", "resume_download", f"Failed: {str(e)}", gid=request.json.get('gid'))
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/remove', methods=['POST'])
def remove_download():
    try:
        gid = request.json.get('gid')
        # Check if it's in history
        in_history = False
        for i, task in enumerate(history_log):
            if task['gid'] == gid:
                del history_log[i]
                in_history = True
                break

        if in_history:
             log("info", "remove_download", "Removed from history", gid=gid)
             return jsonify({"status": "removed", "gid": gid})

        s.aria2.forceRemove(gid)
        log("info", "remove_download", "Download removed", gid=gid)
        return jsonify({"status": "removed", "gid": gid})
    except xmlrpc.client.Fault as e:
        # Check if this is a "GID not found" error (common when frontend has stale tasks)
        if 'not found' in str(e).lower():
            log("info", "remove_download", "GID not found (already removed or from previous session)", gid=request.json.get('gid'))
            # Return success anyway since the goal (task not present) is achieved
            return jsonify({"status": "removed", "gid": request.json.get('gid')})
        else:
            # Log other aria2 faults as errors
            log("error", "remove_download", f"Aria2 error: {str(e)}", gid=request.json.get('gid'))
            return jsonify({"error": str(e)}), 500
    except Exception as e:
        log("error", "remove_download", f"Failed: {str(e)}", gid=request.json.get('gid'))
        return jsonify({"error": str(e)}), 500

@app.route('/api/drive/info', methods=['GET'])
def drive_info():
    try:
        # Check usage of DRIVE_DIR since that's where we store files
        total, used, free = shutil.disk_usage(DRIVE_DIR)
        return jsonify({
            "total": total,
            "used": used,
            "free": free
        })
    except Exception as e:
        # Fallback to root or temp
        try:
             total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
             return jsonify({"total": total, "used": used, "free": free})
        except:
             return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
def cleanup_all():
    """Nuclear option: Remove ALL tasks from aria2 and start fresh"""
    try:
        # Get all tasks
        active = s.aria2.tellActive(["gid"])
        waiting = s.aria2.tellWaiting(0, 9999, ["gid"])
        stopped = s.aria2.tellStopped(0, 9999, ["gid"])
        
        removed_count = 0
        
        # Force remove all active and waiting
        for task in active + waiting:
            try:
                s.aria2.forceRemove(task['gid'])
                removed_count += 1
            except:
                pass
        
        # Purge all stopped
        try:
            s.aria2.purgeDownloadResult()
            removed_count += len(stopped)
        except:
            pass

        history_log.clear()
        processed_gids.clear()
        
        log("info", "cleanup_all", f"Cleaned up {removed_count} tasks")
        return jsonify({"status": "success", "removed": removed_count})
    except Exception as e:
        log("error", "cleanup_all", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

def purge_stalled_downloads():
    """Automatically remove stalled/failed downloads"""
    try:
        stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "errorCode", "completedLength", "totalLength"])
        
        purged = 0
        for task in stopped:
            # Remove completed or errored tasks
            if task['status'] in ['complete', 'error', 'removed']:
                try:
                    s.aria2.removeDownloadResult(task['gid'])
                    purged += 1
                except:
                    pass
        
        if purged > 0:
            log("info", "auto_purge", f"Automatically purged {purged} completed/failed tasks")
            
    except Exception as e:
        pass  # Silent fail for background cleanup

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    
    # Clean up any existing stalled tasks on startup
    log("info", "startup", "Cleaning up stalled tasks from previous session...")
    purge_stalled_downloads()
    
    # Use threaded=True for better concurrent handling
    app.run(port=5000, threaded=True)
