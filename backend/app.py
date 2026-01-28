import xmlrpc.client
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
import base64
import json
from datetime import datetime
from collections import deque
import threading
import time

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_DIR = "/content/temp_downloads"
DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)

# Transfer Status Tracking
# {gid: {status: 'moving'|'moved'|'failed', dest: path, error: msg, name: str}}
transfer_status = {}

# Drive Info Cache
drive_info_cache = {
    "timestamp": 0,
    "data": {"total": 0, "used": 0, "free": 0}
}

# Connect to Aria2 RPC
s = xmlrpc.client.ServerProxy(ARIA2_RPC_URL)

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

class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

    def run(self):
        log("info", "monitor", "Background Monitor started")
        while self.running:
            try:
                self.check_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor crashed: {str(e)}")
            time.sleep(5)

    def check_downloads(self):
        try:
            # Get stopped tasks (complete, error, removed)
            # We need totalLength to confirm it wasn't a zero-byte error
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "bittorrent", "totalLength"])

            for task in stopped:
                gid = task['gid']
                status = task['status']

                # Only process COMPLETED tasks that we haven't processed yet
                if status == 'complete':
                    if gid not in transfer_status:
                        self.move_to_drive(task)
                    elif transfer_status[gid].get('status') in ['moved', 'failed']:
                         # Cleanup from Aria2 only after move attempt is done (success or fail)
                         try:
                            s.aria2.removeDownloadResult(gid)
                         except:
                            pass
        except Exception as e:
            # Aria2 might not be ready yet or connection failed
            pass

    def move_to_drive(self, task):
        gid = task['gid']
        files = task.get('files', [])
        if not files:
            return

        # Determine source path
        # Aria2 files list has absolute paths.
        source_path = files[0]['path']

        # Safety check: ensure it is inside DOWNLOAD_DIR
        if not source_path.startswith(DOWNLOAD_DIR):
             return

        # Calculate relative path to find top-level directory/file
        rel_path = os.path.relpath(source_path, DOWNLOAD_DIR)
        top_level = rel_path.split(os.sep)[0]
        full_source = os.path.join(DOWNLOAD_DIR, top_level)

        # Ensure Drive directory exists
        if not os.path.exists(DRIVE_DIR):
            try:
                os.makedirs(DRIVE_DIR, exist_ok=True)
            except:
                pass

        dest_path = os.path.join(DRIVE_DIR, top_level)

        transfer_status[gid] = {"status": "moving", "source": full_source, "name": top_level}
        log("info", "mover", f"Moving {top_level} to Drive...", gid=gid)

        try:
            # Handle collisions
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(top_level)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_name = f"{base}_{timestamp}{ext}"
                dest_path = os.path.join(DRIVE_DIR, new_name)

            # Move
            shutil.move(full_source, dest_path)

            transfer_status[gid] = {
                "status": "moved",
                "dest": dest_path,
                "name": top_level,
                "timestamp": datetime.now().isoformat()
            }
            log("info", "mover", f"Moved to {dest_path}", gid=gid)

        except Exception as e:
            transfer_status[gid] = {"status": "failed", "error": str(e), "name": top_level}
            log("error", "mover", f"Move failed: {str(e)}", gid=gid)

# Start Monitor
monitor = BackgroundMonitor()
monitor.start()

@app.before_request
def check_auth():
    if request.method == 'OPTIONS':
        return
    if request.path == '/health':
        return

    api_key = os.environ.get('CLOUDLEECHER_API_KEY')
    if not api_key:
        # If no key configured in env, allow open access (but warn in logs if we wanted)
        return

    client_key = request.headers.get('x-api-key')
    if client_key != api_key:
        return jsonify({"error": "Unauthorized"}), 401

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
        gid = s.aria2.addUri([magnet_link])
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
        gid = s.aria2.addTorrent(binary_torrent)
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
        
        # --- Merge Transfer Status ---
        current_active_gids = set(t['gid'] for t in active)
        current_stopped_gids = set(t['gid'] for t in stopped)

        for gid, info in transfer_status.items():
            if info['status'] == 'moving':
                if gid not in current_active_gids:
                    active.append({
                        "gid": gid,
                        "status": "moving",
                        "name": info.get('name', 'Unknown'),
                        "totalLength": "100", # Dummy values
                        "completedLength": "50",
                        "downloadSpeed": "0",
                        "infoHash": "moving_placeholder",
                        "progress": 50 # Just visual
                    })
            elif info['status'] == 'moved':
                 if gid not in current_stopped_gids:
                    stopped.append({
                        "gid": gid,
                        "status": "saved",
                        "name": info.get('name', 'Unknown'),
                        "totalLength": "100",
                        "completedLength": "100",
                        "errorCode": "0"
                    })
            elif info['status'] == 'failed':
                 if gid not in current_stopped_gids:
                    stopped.append({
                        "gid": gid,
                        "status": "error",
                        "name": info.get('name', 'Unknown'),
                        "errorMessage": f"Move failed: {info.get('error')}"
                    })

        # --- End Merge ---

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
            log_msg = f"Currently tracking {len(all_gids)} tasks"
            if gid_transitions:
                log_msg += f" | Transitions: {', '.join(gid_transitions)}"
            # log("info", "status_poll", log_msg, extra={"gids": all_gids}) # Reduce log noise
        
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
    global drive_info_cache
    now = time.time()

    # Cache for 60 seconds
    if now - drive_info_cache['timestamp'] > 60:
        try:
            # Check DRIVE_DIR specifically
            total, used, free = shutil.disk_usage(DRIVE_DIR)
            drive_info_cache['data'] = {
                "total": total,
                "used": used,
                "free": free
            }
            drive_info_cache['timestamp'] = now
        except Exception as e:
            # On failure (e.g., Drive not mounted), return zeros or last known
            # But try to be safe
            pass

    return jsonify(drive_info_cache['data'])

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
        
        # Also clear temp downloads if we are nuking
        try:
            for item in os.listdir(DOWNLOAD_DIR):
                path = os.path.join(DOWNLOAD_DIR, item)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        except:
            pass

        log("info", "cleanup_all", f"Cleaned up {removed_count} tasks and temp files")
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
    
    # Ensure directories exist
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(DRIVE_DIR, exist_ok=True)

    # Clean up any existing stalled tasks on startup
    log("info", "startup", "Cleaning up stalled tasks from previous session...")
    purge_stalled_downloads()
    
    app.run(port=5000)
