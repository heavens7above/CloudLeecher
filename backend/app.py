import xmlrpc.client
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
import base64
import json
import time
import threading
import functools
from datetime import datetime
from collections import deque

app = Flask(__name__)
CORS(app)

# Configuration
# Use local temp storage for downloads to avoid Drive FUSE issues
TEMP_DOWNLOAD_DIR = "/content/temp_downloads"
# Final destination on Google Drive
FINAL_DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"
HISTORY_FILE = "/content/download_history.json"
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY", "default-dev-key")

# Ensure temp dir exists
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(FINAL_DRIVE_DIR, exist_ok=True)

# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)
# History of completed/moved tasks
history = []

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

def load_history():
    """Load history from disk"""
    global history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                history = json.load(f)
        except Exception as e:
            log("error", "load_history", f"Failed to load history: {e}")
            history = []

def save_history():
    """Save history to disk"""
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f)
    except Exception as e:
        log("error", "save_history", f"Failed to save history: {e}")

# Load history on startup
load_history()

def require_api_key(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        # Check header
        request_key = request.headers.get('x-api-key')
        if not request_key or request_key != API_KEY:
             log("warning", "auth", "Unauthorized access attempt", extra={"ip": request.remote_addr})
             return jsonify({"error": "Unauthorized: Invalid API Key"}), 401
        return f(*args, **kwargs)
    return decorated_function

class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.lock = threading.Lock()

    def run(self):
        log("info", "monitor", "Background monitor started")
        while self.running:
            try:
                self.check_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor loop error: {e}")
            time.sleep(5)  # Poll every 5 seconds

    def check_downloads(self):
        try:
            # Get stopped tasks (includes complete and error)
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength", "dir"])

            for task in stopped:
                if task['status'] == 'complete':
                    self.handle_complete(task)
                elif task['status'] == 'error':
                    # Log error but let user clean up manually or auto-purge if desired
                    pass
        except Exception as e:
            # log("error", "monitor", f"Failed to query aria2: {e}") # Reduce spam
            pass

    def handle_complete(self, task):
        gid = task['gid']

        # Check if already processed
        if any(h['gid'] == gid for h in history):
            # Already in history, ensure removed from aria2
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass
            return

        # Start moving process
        log("info", "monitor", "Processing completed download", gid=gid)

        # 1. Update history to 'moving'
        task_info = {
            "gid": gid,
            "name": self.get_task_name(task),
            "status": "moving",
            "totalLength": task['totalLength'],
            "completedLength": task['totalLength'], # It's complete
            "downloadSpeed": 0,
            "timestamp": datetime.now().isoformat()
        }

        # Add to history (remove old entry if exists)
        self.update_history(task_info)

        # 2. Move file(s)
        try:
            source_path = task['files'][0]['path']
            # If multi-file torrent, source_path is one file, but we usually want the root dir.
            # However, aria2 returns the full path of the first file.
            # We need to find the root directory of the download.
            # If aria2 dir is TEMP_DOWNLOAD_DIR, then:
            # Single file: TEMP_DOWNLOAD_DIR/filename
            # Multi file: TEMP_DOWNLOAD_DIR/dirname/filename

            # Simple heuristic:
            # Get the relative path from the config dir
            # But aria2 returns absolute path in 'files'

            # Use 'dir' from task info if available, else configured TEMP
            download_base = task.get('dir', TEMP_DOWNLOAD_DIR)

            # Determine what to move.
            # If it's a single file torrent, move the file.
            # If it's a directory, move the directory.

            # Get the path component relative to download_base
            rel_path = os.path.relpath(source_path, download_base)
            root_component = rel_path.split(os.sep)[0]

            source_item = os.path.join(download_base, root_component)
            dest_item = os.path.join(FINAL_DRIVE_DIR, root_component)

            if not os.path.exists(source_item):
                log("error", "monitor", f"Source not found: {source_item}", gid=gid)
                # Mark as error in history
                task_info['status'] = 'error'
                task_info['errorMessage'] = "Source file missing"
                self.update_history(task_info)
                # Remove from aria2 to avoid infinite loop
                s.aria2.removeDownloadResult(gid)
                return

            # Handle collision
            if os.path.exists(dest_item):
                base, ext = os.path.splitext(dest_item)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_item = f"{base}_{timestamp}{ext}"
                log("warning", "monitor", f"Destination exists, renaming to {os.path.basename(dest_item)}", gid=gid)

            log("info", "monitor", f"Moving {source_item} to {dest_item}", gid=gid)
            shutil.move(source_item, dest_item)

            # 3. Update history to 'saved'
            task_info['status'] = 'saved'
            task_info['errorMessage'] = None
            self.update_history(task_info)
            log("info", "monitor", "Move successful", gid=gid)

            # 4. Remove from Aria2
            s.aria2.removeDownloadResult(gid)

        except Exception as e:
            log("error", "monitor", f"Move failed: {e}", gid=gid)
            task_info['status'] = 'error'
            task_info['errorMessage'] = str(e)
            self.update_history(task_info)
            # We don't remove from Aria2 immediately if it failed?
            # Actually we should, otherwise we loop. We rely on history for status.
            s.aria2.removeDownloadResult(gid)

    def get_task_name(self, task):
        try:
            # Try bittorrent name first
            if 'bittorrent' in task and 'info' in task['bittorrent'] and 'name' in task['bittorrent']['info']:
                return task['bittorrent']['info']['name']
            # Fallback to file name
            if 'files' in task and len(task['files']) > 0:
                return os.path.basename(task['files'][0]['path'])
        except:
            pass
        return "Unknown"

    def update_history(self, task_info):
        global history
        # Remove existing entry with same GID
        history = [h for h in history if h['gid'] != task_info['gid']]
        # Add new
        history.append(task_info)
        # Trim history
        if len(history) > 50:
            history.pop(0)
        save_history()

# Start background monitor
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
        # Force download to temp dir
        options = {"dir": TEMP_DOWNLOAD_DIR}
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
        # Force download to temp dir
        options = {"dir": TEMP_DOWNLOAD_DIR}
        gid = s.aria2.addTorrent(binary_torrent, [], options)
        log("info", "add_torrent_file", "Torrent file added successfully, downloading metadata...", gid=gid)
        
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
        # stopped = s.aria2.tellStopped(0, 100, basic_keys) # We don't need aria2 stopped mostly, as we process them.
        # But if we fail to process, they might be there.
        stopped_aria2 = s.aria2.tellStopped(0, 100, basic_keys)
        
        # Merge our history (saved/moving/error) into 'stopped' so frontend sees them
        # Frontend expects lists.
        
        # Filter out history items that might still be in aria2 stopped list (race condition)
        # Use a map for uniqueness
        stopped_map = {}
        for t in stopped_aria2:
            stopped_map[t['gid']] = t
        
        for h in history:
            stopped_map[h['gid']] = h

        stopped = list(stopped_map.values())
        
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

        # Check if it's in history
        global history
        in_history = False
        for i, h in enumerate(history):
            if h['gid'] == gid:
                history.pop(i)
                in_history = True
                save_history()
                break

        if in_history:
             log("info", "remove_download", "Removed from history", gid=gid)
             return jsonify({"status": "removed", "gid": gid})

        s.aria2.forceRemove(gid)
        log("info", "remove_download", "Download removed", gid=gid)
        return jsonify({"status": "removed", "gid": gid})
    except xmlrpc.client.Fault as e:
        if 'not found' in str(e).lower():
            log("info", "remove_download", "GID not found (already removed)", gid=request.json.get('gid'))
            return jsonify({"status": "removed", "gid": request.json.get('gid')})
        else:
            log("error", "remove_download", f"Aria2 error: {str(e)}", gid=request.json.get('gid'))
            return jsonify({"error": str(e)}), 500
    except Exception as e:
        log("error", "remove_download", f"Failed: {str(e)}", gid=request.json.get('gid'))
        return jsonify({"error": str(e)}), 500

@app.route('/api/drive/info', methods=['GET'])
@require_api_key
def drive_info():
    try:
        total, used, free = shutil.disk_usage(FINAL_DRIVE_DIR)
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
        # Clear history
        global history
        history = []
        save_history()

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
        
        log("info", "cleanup_all", f"Cleaned up {removed_count} tasks")
        return jsonify({"status": "success", "removed": removed_count})
    except Exception as e:
        log("error", "cleanup_all", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    app.run(port=5000)
