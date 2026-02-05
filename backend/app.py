import xmlrpc.client
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
import base64
import json
import threading
import time
from datetime import datetime
from collections import deque
from functools import wraps

app = Flask(__name__)
CORS(app)

# Configuration
DOWNLOAD_DIR = "/content/temp_downloads" # Local SSD for high speed & reliability
DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"
HISTORY_FILE = "/content/download_history.json"
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY")

# Ensure directories exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(DRIVE_DIR, exist_ok=True)

# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)

# Task History (Persisted)
task_history = {}
history_lock = threading.Lock()

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
        pass
    
    # Print to console for Colab visibility
    print(f"[{level.upper()}] {operation}: {message}" + (f" (GID: {gid})" if gid else ""))

def load_history():
    global task_history
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                task_history = json.load(f)
            log("info", "history", f"Loaded {len(task_history)} tasks from history")
        except Exception as e:
            log("error", "history", f"Failed to load history: {e}")

def save_history():
    with history_lock:
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(task_history, f)
        except Exception as e:
            log("error", "history", f"Failed to save history: {e}")

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if API_KEY:
            request_key = request.headers.get('x-api-key')
            if not request_key or request_key != API_KEY:
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

    def run(self):
        log("info", "monitor", "Background monitor started")
        while self.running:
            try:
                self.check_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor loop error: {e}")
            time.sleep(2)

    def check_downloads(self):
        # Get all tasks from Aria2
        try:
            # We check stopped tasks because that's where completed ones end up
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength", "completedLength", "errorCode", "errorMessage"])
            active = s.aria2.tellActive(["gid", "status", "totalLength", "completedLength"])
            waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
        except Exception as e:
            # Aria2 might be down or busy
            return

        # Update active/waiting tasks in history for progress tracking (optional, but good for restart recovery)
        with history_lock:
            for task in active + waiting:
                if task['gid'] not in task_history:
                     task_history[task['gid']] = {
                        "gid": task['gid'],
                        "status": task['status'],
                        "name": "Initializing...", # Will be updated
                        "totalLength": task.get("totalLength", "0"),
                        "completedLength": task.get("completedLength", "0"),
                        "timestamp": datetime.now().isoformat()
                     }

            # Process stopped tasks (Completed, Error, Removed)
            for task in stopped:
                gid = task['gid']
                status = task['status']

                # Update history info
                if gid not in task_history:
                     task_history[gid] = {
                        "gid": gid,
                        "status": status,
                        "timestamp": datetime.now().isoformat()
                     }

                # Logic for Completed Tasks
                if status == 'complete':
                    # Check if already processed/saved
                    if task_history[gid].get('status') == 'saved':
                        # Already moved, just ensure it's removed from Aria2
                        try:
                            s.aria2.removeDownloadResult(gid)
                        except:
                            pass
                        continue

                    log("info", "monitor", "Download complete. Moving to Drive...", gid=gid)

                    # Determine source and destination
                    files = task.get('files', [])
                    if not files:
                        continue

                    # Aria2 usually returns the primary file path.
                    # If it's a multi-file torrent, the first file usually indicates the folder.
                    # We need to find what exactly was downloaded to DOWNLOAD_DIR

                    source_path = files[0]['path']
                    # source_path is absolute.

                    # Security check: Ensure we are only moving things inside DOWNLOAD_DIR
                    if not source_path.startswith(DOWNLOAD_DIR):
                        log("error", "monitor", f"Suspicious path: {source_path}", gid=gid)
                        continue

                    # Determine relative path from DOWNLOAD_DIR
                    # e.g., /content/temp/MyMovie/movie.mp4 -> MyMovie/movie.mp4
                    # e.g., /content/temp/movie.mp4 -> movie.mp4
                    rel_path = os.path.relpath(source_path, DOWNLOAD_DIR)

                    # We want to move the top-level item (file or folder)
                    top_level_name = rel_path.split(os.sep)[0]
                    full_source_path = os.path.join(DOWNLOAD_DIR, top_level_name)

                    if not os.path.exists(full_source_path):
                         log("warning", "monitor", f"Source not found: {full_source_path}", gid=gid)
                         # Maybe it was already moved?
                         s.aria2.removeDownloadResult(gid)
                         continue

                    # Destination logic with collision handling
                    dest_path = os.path.join(DRIVE_DIR, top_level_name)

                    if os.path.exists(dest_path):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        name_part, ext_part = os.path.splitext(top_level_name)
                        new_name = f"{name_part}_{timestamp}{ext_part}"
                        dest_path = os.path.join(DRIVE_DIR, new_name)
                        log("info", "monitor", f"Collision detected. Renaming to {new_name}", gid=gid)

                    # Perform the Move
                    try:
                        # Update status to 'moving'
                        task_history[gid]['status'] = 'moving'
                        task_history[gid]['name'] = top_level_name

                        log("info", "monitor", f"Moving {full_source_path} to {dest_path}", gid=gid)
                        shutil.move(full_source_path, dest_path)

                        log("info", "monitor", "Move successful", gid=gid)
                        task_history[gid]['status'] = 'saved'
                        task_history[gid]['final_path'] = dest_path
                        save_history()

                        # Cleanup Aria2
                        s.aria2.removeDownloadResult(gid)

                    except Exception as e:
                        log("error", "monitor", f"Move failed: {e}", gid=gid)
                        task_history[gid]['status'] = 'error'
                        task_history[gid]['errorMessage'] = f"Move failed: {str(e)}"
                        save_history()

                elif status in ['error', 'removed']:
                    # Just update history and clear from Aria2
                    task_history[gid]['status'] = status
                    task_history[gid]['errorCode'] = task.get('errorCode')
                    task_history[gid]['errorMessage'] = task.get('errorMessage')

                    try:
                        s.aria2.removeDownloadResult(gid)
                    except:
                        pass
                    save_history()

# Start Monitor
load_history()
monitor = BackgroundMonitor()
monitor.start()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "CloudLeecher-Backend"})

@app.route('/api/logs', methods=['GET'])
@require_api_key
def get_logs():
    return jsonify({"logs": list(logs)})

@app.route('/api/download/magnet', methods=['POST'])
@require_api_key
def add_magnet():
    data = request.json
    magnet_link = data.get('magnet')
    if not magnet_link:
        return jsonify({"error": "Magnet link is required"}), 400
    
    # Check active downloads
    try:
        active = s.aria2.tellActive(["gid"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid"])
        if len(active) > 0 or len(waiting) > 0:
             return jsonify({"error": "Queue full. Wait for current download."}), 429

        gid = s.aria2.addUri([magnet_link], {"dir": DOWNLOAD_DIR})
        log("info", "add_magnet", "Added magnet", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", f"Failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
@require_api_key
def add_torrent_file():
    try:
        data = request.json
        b64_content = data.get('torrent')
        if not b64_content:
            return jsonify({"error": "Content required"}), 400

        active = s.aria2.tellActive(["gid"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid"])
        if len(active) > 0 or len(waiting) > 0:
             return jsonify({"error": "Queue full"}), 429

        raw_bytes = base64.b64decode(b64_content)
        gid = s.aria2.addTorrent(xmlrpc.client.Binary(raw_bytes), [], {"dir": DOWNLOAD_DIR})
        log("info", "add_torrent", "Added torrent file", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent", f"Failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
@require_api_key
def get_status():
    try:
        # Get live status
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode"]

        try:
            active = s.aria2.tellActive(basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"])
            waiting = s.aria2.tellWaiting(0, 100, basic_keys)
            stopped = s.aria2.tellStopped(0, 100, basic_keys) # Should be empty mostly due to monitor
        except:
            active, waiting, stopped = [], [], []

        # Merge with history
        # We want to show tasks from history that are NOT in active/waiting
        # And also update history with latest active info
        
        live_gids = set(t['gid'] for t in active + waiting + stopped)
        
        # Add historical tasks (completed/saved/error)
        # Convert dict to list
        history_list = []
        with history_lock:
             for gid, task in task_history.items():
                 if gid not in live_gids:
                     # This task is fully handled by history now
                     history_list.append(task)
        
        # Construct response: Active/Waiting from Aria2, Stopped from History (mostly)
        # But we can just return lists. Frontend handles merging mostly, but we can structure it.
        
        # Actually, let's inject "saved" tasks into the "stopped" list for the frontend
        for h_task in history_list:
            if h_task['status'] in ['saved', 'error', 'removed']:
                # Adapt to Aria2 format
                adapted = {
                    "gid": h_task['gid'],
                    "status": h_task['status'], # saved is custom, frontend should handle
                    "totalLength": h_task.get("totalLength", "0"),
                    "completedLength": h_task.get("completedLength", "0"),
                    "files": [{"path": h_task.get("name", "Unknown")}],
                    "errorMessage": h_task.get("errorMessage"),
                    "errorCode": h_task.get("errorCode")
                }
                stopped.append(adapted)
        
        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        log("error", "get_status", f"Failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
@require_api_key
def pause_download():
    try:
        gid = request.json.get('gid')
        s.aria2.pause(gid)
        return jsonify({"status": "paused", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
@require_api_key
def resume_download():
    try:
        gid = request.json.get('gid')
        s.aria2.unpause(gid)
        return jsonify({"status": "resumed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/remove', methods=['POST'])
@require_api_key
def remove_download():
    try:
        gid = request.json.get('gid')
        # Try aria2 first
        try:
            s.aria2.forceRemove(gid)
        except:
            pass

        # Update history
        with history_lock:
            if gid in task_history:
                task_history[gid]['status'] = 'removed'
        save_history()

        return jsonify({"status": "removed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/drive/info', methods=['GET'])
@require_api_key
def drive_info():
    try:
        total, used, free = shutil.disk_usage(DRIVE_DIR)
        return jsonify({"total": total, "used": used, "free": free})
    except:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
@require_api_key
def cleanup_all():
    try:
        s.aria2.purgeDownloadResult()
        with history_lock:
            task_history.clear()
        save_history()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    app.run(port=5000)
