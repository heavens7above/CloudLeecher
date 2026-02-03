import xmlrpc.client
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
import base64
import json
import time
import threading
from datetime import datetime
from collections import deque
from functools import wraps

app = Flask(__name__)
CORS(app)

# Configuration
# Aria2 downloads here first (local fast disk)
TEMP_DIR = "/content/temp_downloads"
# Final destination (Google Drive)
FINAL_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# Ensure directories exist
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(FINAL_DIR, exist_ok=True)

# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)

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

# --- Authentication Middleware ---
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = os.environ.get('CLOUDLEECHER_API_KEY')
        # If no key is set in env, we might be in dev mode or insecure mode,
        # but for production hardening we should enforce it if it exists.
        # If the notebook didn't set it, we default to open (or we could enforce generating one).
        # For now, if the env var exists, we check it.
        if api_key:
            request_key = request.headers.get('x-api-key')
            if not request_key or request_key != api_key:
                return jsonify({"error": "Unauthorized: Invalid API Key"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Background Monitor for Move-to-Drive ---
class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.moving_tasks = {} # gid -> task_info
        self.saved_tasks = {}  # gid -> task_info
        self.lock = threading.Lock()

    def run(self):
        log("info", "monitor", "Background monitor started")
        while True:
            try:
                self.check_completed_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor loop error: {str(e)}")
            time.sleep(5)

    def check_completed_downloads(self):
        try:
            # Get stopped tasks to find completed ones
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength", "completedLength", "errorCode", "errorMessage"])

            for task in stopped:
                gid = task['gid']

                # We only care about 'complete' tasks
                if task['status'] == 'complete':

                    # Check if already processing or processed
                    with self.lock:
                        if gid in self.moving_tasks or gid in self.saved_tasks:
                            continue

                        # Mark as moving
                        self.moving_tasks[gid] = {
                            "gid": gid,
                            "name": self.get_task_name(task),
                            "status": "moving",
                            "totalLength": task['totalLength'],
                            "completedLength": task['completedLength'],
                            "progress": 100,
                            "speed": 0
                        }

                    # Start move operation in a separate thread to not block the monitor loop
                    threading.Thread(target=self.move_to_drive, args=(gid, task)).start()

                # We could also auto-clean errors here if we wanted

        except Exception as e:
            log("error", "monitor_check", f"Failed to check downloads: {str(e)}")

    def get_task_name(self, task):
        if task.get('files') and len(task['files']) > 0:
            return os.path.basename(task['files'][0]['path'])
        return "Unknown"

    def move_to_drive(self, gid, task):
        log("info", "move_to_drive", "Starting move to Drive", gid=gid)

        try:
            files = task.get('files', [])
            if not files:
                log("warning", "move_to_drive", "No files found for task", gid=gid)
                self._mark_saved(gid, success=False, error="No files found")
                return

            # Determine source path (usually the first file's path or directory)
            # Aria2 structure: if single file, path is full path. If multi-file, it's inside a dir.
            # However, we set --dir=TEMP_DIR.
            # If multi-file torrent, aria2 creates a subdir in TEMP_DIR.
            # If single-file, it creates the file in TEMP_DIR.

            source_path = files[0]['path']

            # Check if the source path exists
            if not os.path.exists(source_path):
                 log("error", "move_to_drive", f"Source not found: {source_path}", gid=gid)
                 # Wait a bit, maybe file system lag?
                 time.sleep(2)
                 if not os.path.exists(source_path):
                     self._mark_saved(gid, success=False, error="Source file missing")
                     # Remove from aria2 to stop retry loops
                     try: s.aria2.removeDownloadResult(gid)
                     except: pass
                     return

            # Determine what to move.
            # If it's a multi-file torrent, we want to move the top-level directory.
            # If aria2 reports path as "TEMP_DIR/MyMovie/video.mp4", and "TEMP_DIR/MyMovie/subs.srt"
            # We want to move "TEMP_DIR/MyMovie".

            # Logic: Get the relative path from TEMP_DIR
            rel_path = os.path.relpath(source_path, TEMP_DIR)
            top_level_name = rel_path.split(os.sep)[0]
            move_source = os.path.join(TEMP_DIR, top_level_name)
            move_dest = os.path.join(FINAL_DIR, top_level_name)

            log("info", "move_to_drive", f"Moving {move_source} -> {move_dest}", gid=gid)

            # Handle collision
            if os.path.exists(move_dest):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name, ext = os.path.splitext(top_level_name)
                # If it's a directory, ext is empty usually, but splitext works.
                if os.path.isdir(move_source):
                    new_name = f"{top_level_name}_{timestamp}"
                else:
                    new_name = f"{name}_{timestamp}{ext}"
                move_dest = os.path.join(FINAL_DIR, new_name)
                log("warning", "move_to_drive", f"Destination exists, renaming to {new_name}", gid=gid)

            # Perform Move
            shutil.move(move_source, move_dest)

            # Success
            log("info", "move_to_drive", "Move completed successfully", gid=gid)
            self._mark_saved(gid, success=True)

            # Clean up Aria2 record
            try:
                s.aria2.removeDownloadResult(gid)
            except Exception as e:
                log("warning", "cleanup", f"Failed to remove result from Aria2: {e}", gid=gid)

        except Exception as e:
            log("error", "move_to_drive", f"Move failed: {str(e)}", gid=gid)
            self._mark_saved(gid, success=False, error=str(e))

    def _mark_saved(self, gid, success=True, error=None):
        with self.lock:
            if gid in self.moving_tasks:
                task = self.moving_tasks.pop(gid)
                task['status'] = 'saved' if success else 'error'
                if error:
                    task['errorMessage'] = error
                self.saved_tasks[gid] = task

monitor = BackgroundMonitor()
monitor.start()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "CloudLeecher-Backend"})

@app.route('/api/logs', methods=['GET'])
@require_api_key
def get_logs():
    """Return recent backend logs for frontend inspection"""
    try:
        return jsonify({"logs": list(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/magnet', methods=['POST'])
@require_api_key
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
        options = {"dir": TEMP_DIR}
        gid = s.aria2.addUri([magnet_link], options)
        log("info", "add_magnet", "Magnet link added successfully", gid=gid, extra={"magnet": magnet_link[:50] + "..."})
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", f"Failed: {str(e)}", extra={"magnet": magnet_link[:50] + "..."})
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
@require_api_key
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
        options = {"dir": TEMP_DIR}
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
@require_api_key
def get_status():
    try:
        # Use safe keys for non-active tasks to avoid API errors/empty responses
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(extended_keys)
        waiting = s.aria2.tellWaiting(0, 100, basic_keys)
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
        # Merge with local Moving/Saved tasks
        # We inject them into the 'stopped' or separate lists?
        # The frontend handles lists. Let's return them in 'stopped' or a new list?
        # Existing frontend expects {active, waiting, stopped}.
        # If we put 'moving' and 'saved' tasks into 'stopped' list, the frontend should handle them if it just iterates.

        local_tasks = []
        with monitor.lock:
             local_tasks.extend(monitor.moving_tasks.values())
             local_tasks.extend(monitor.saved_tasks.values())

        # Prepend local tasks to stopped so they appear
        stopped = local_tasks + stopped

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
            
        if all_gids:
            log_msg = f"Currently tracking {len(all_gids)} tasks"
            if gid_transitions:
                log_msg += f" | Transitions: {', '.join(gid_transitions)}"
            # Reduce log spam
            # log("info", "status_poll", log_msg, extra={"gids": all_gids})
        
        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        log("error", "get_status", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
@require_api_key
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
@require_api_key
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
@require_api_key
def remove_download():
    try:
        gid = request.json.get('gid')

        # Check if it's a local task (moving/saved)
        with monitor.lock:
            if gid in monitor.moving_tasks:
                # Can't easily stop a shutil.move, but we can remove it from list so it disappears
                del monitor.moving_tasks[gid]
                log("info", "remove_download", "Removed moving task from tracking", gid=gid)
                return jsonify({"status": "removed", "gid": gid})
            if gid in monitor.saved_tasks:
                del monitor.saved_tasks[gid]
                log("info", "remove_download", "Removed saved task from history", gid=gid)
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
@require_api_key
def drive_info():
    try:
        # Check drive info on the Final Dir
        total, used, free = shutil.disk_usage(FINAL_DIR)
        return jsonify({
            "total": total,
            "used": used,
            "free": free
        })
    except Exception as e:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
@require_api_key
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
        
        # Clear local tracking
        with monitor.lock:
            monitor.moving_tasks.clear()
            monitor.saved_tasks.clear()

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
            # Note: We should be careful not to remove 'complete' tasks before the monitor picks them up!
            # The monitor checks every 5s. This runs on startup.
            if task['status'] in ['error', 'removed']:
                try:
                    s.aria2.removeDownloadResult(task['gid'])
                    purged += 1
                except:
                    pass
        
        if purged > 0:
            log("info", "auto_purge", f"Automatically purged {purged} failed tasks")
            
    except Exception as e:
        pass  # Silent fail for background cleanup

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    
    # Clean up any existing stalled tasks on startup
    log("info", "startup", "Cleaning up stalled tasks from previous session...")
    purge_stalled_downloads()
    
    app.run(port=5000)
