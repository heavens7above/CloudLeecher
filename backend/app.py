import xmlrpc.client
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import os
import shutil
import base64
import json
import time
import threading
import secrets
from datetime import datetime
from collections import deque

app = Flask(__name__)
CORS(app)

# --- Configuration ---
# Use a local path for high-speed download (SSD), then move to Drive
TEMP_DOWNLOAD_DIR = "/content/temp_downloads"
FINAL_DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# API Security
API_KEY = os.environ.get("CL_API_KEY") or secrets.token_urlsafe(12)

# Ensure directories exist
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(FINAL_DRIVE_DIR, exist_ok=True)

# --- State Management ---
# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)

# Track tasks that are currently being moved to Drive
# Format: gid -> { name: str, size: int, start_time: float }
uploading_tasks = {}
uploading_lock = threading.Lock()

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

# --- Authentication Middleware ---
@app.before_request
def check_auth():
    if request.method == 'OPTIONS':
        return

    # Allow health check without auth for initial connectivity test (optional, but stricter is better)
    if request.endpoint == 'health':
        return

    # Check Header
    key = request.headers.get('x-api-key')
    if key != API_KEY:
        # Also allow query param for convenience if needed, but header is preferred
        return jsonify({"error": "Unauthorized"}), 401

# --- Background Monitor ---
class DownloadMonitor(threading.Thread):
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
                log("error", "monitor", f"Monitor loop failed: {e}")
            time.sleep(2)

    def check_downloads(self):
        # 1. Get completed tasks from Aria2
        try:
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength"])
        except Exception:
            return

        for task in stopped:
            gid = task['gid']
            status = task['status']

            if status == 'complete':
                # Check if already processing
                with uploading_lock:
                    if gid in uploading_tasks:
                        continue

                    # Mark as uploading
                    files = task.get('files', [])
                    if not files:
                        continue

                    # Determine source path (usually the first file's directory or file itself)
                    # Aria2 structure: files[0]['path']
                    source_path = files[0]['path']

                    # If it's a directory download, aria2 returns files inside.
                    # We need to find the root folder in TEMP_DOWNLOAD_DIR
                    # Assumption: aria2 downloads to TEMP_DOWNLOAD_DIR/TaskName or TEMP_DOWNLOAD_DIR/File

                    # Robust path finding:
                    rel_path = os.path.relpath(source_path, TEMP_DOWNLOAD_DIR)
                    root_name = rel_path.split(os.sep)[0]
                    full_source_path = os.path.join(TEMP_DOWNLOAD_DIR, root_name)

                    uploading_tasks[gid] = {
                        "name": root_name,
                        "size": task['totalLength'],
                        "start_time": time.time()
                    }

                # Start upload in a separate thread to not block the monitor loop?
                # Actually, moving might take time. Let's spawn a mover thread per task
                # or just do it here if we want sequential safe moves.
                # Sequential is safer for Colab I/O.

                self.move_to_drive(gid, full_source_path, root_name)

    def move_to_drive(self, gid, source, name):
        log("info", "move", f"Starting move to Drive: {name}", gid=gid)
        dest = os.path.join(FINAL_DRIVE_DIR, name)

        try:
            # Check if destination exists
            if os.path.exists(dest):
                log("warning", "move", f"Destination exists, renaming: {name}", gid=gid)
                base, ext = os.path.splitext(name)
                timestamp = int(time.time())
                dest = os.path.join(FINAL_DRIVE_DIR, f"{base}_{timestamp}{ext}")

            # Perform Move
            shutil.move(source, dest)
            log("info", "move", "Move completed successfully", gid=gid)

            # Clean up from Aria2
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass

        except Exception as e:
            log("error", "move", f"Failed to move file: {e}", gid=gid)
        finally:
            with uploading_lock:
                if gid in uploading_tasks:
                    del uploading_tasks[gid]

# Start Monitor
monitor = DownloadMonitor()
monitor.start()

# --- Routes ---

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "service": "CloudLeecher-Backend",
        "auth_required": True
    })

@app.route('/api/logs', methods=['GET'])
def get_logs():
    return jsonify({"logs": list(logs)})

@app.route('/api/download/magnet', methods=['POST'])
def add_magnet():
    data = request.json
    magnet_link = data.get('magnet')
    if not magnet_link:
        return jsonify({"error": "Magnet link is required"}), 400
    
    try:
        gid = s.aria2.addUri([magnet_link])
        log("info", "add_magnet", "Magnet link added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
def add_torrent_file():
    data = request.json
    b64_content = data.get('torrent')
    if not b64_content:
        return jsonify({"error": "Torrent content required"}), 400

    try:
        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        gid = s.aria2.addTorrent(binary_torrent)
        log("info", "add_torrent_file", "Torrent file added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent_file", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    try:
        # Standard Aria2 Status
        keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "numSeeders", "connections", "infoHash", "bittorrent", "followedBy", "following"]
        
        active = s.aria2.tellActive(keys)
        waiting = s.aria2.tellWaiting(0, 100, keys)
        stopped = s.aria2.tellStopped(0, 100, keys)
        
        # Inject Uploading Tasks
        # We present them as "active" but with a custom status in the frontend if possible,
        # or we return a separate list. Returning a separate list is cleaner, but frontend expects specific structure.
        # Let's inject them into 'active' with a special status 'uploading'
        
        with uploading_lock:
            for gid, info in uploading_tasks.items():
                # Fake an aria2 task object
                upload_task = {
                    "gid": gid,
                    "status": "uploading", # Custom status
                    "totalLength": str(info['size']),
                    "completedLength": str(info['size']), # It's done downloading
                    "downloadSpeed": "0",
                    "uploadSpeed": "0",
                    "files": [{"path": info['name']}],
                    "dir": FINAL_DRIVE_DIR
                }
                # Filter out the stopped task from aria2 if it's still there
                stopped = [t for t in stopped if t['gid'] != gid]
                active.append(upload_task)

        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        log("error", "get_status", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
def pause_download():
    gid = request.json.get('gid')
    try:
        s.aria2.pause(gid)
        return jsonify({"status": "paused", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
def resume_download():
    gid = request.json.get('gid')
    try:
        s.aria2.unpause(gid)
        return jsonify({"status": "resumed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/remove', methods=['POST'])
def remove_download():
    gid = request.json.get('gid')
    try:
        s.aria2.forceRemove(gid)
        return jsonify({"status": "removed", "gid": gid})
    except Exception as e:
        # If not found, it's fine
        return jsonify({"status": "removed", "gid": gid})

@app.route('/api/drive/info', methods=['GET'])
def drive_info():
    try:
        # Check Final Drive Destination
        total, used, free = shutil.disk_usage(FINAL_DRIVE_DIR)
        return jsonify({
            "total": total,
            "used": used,
            "free": free
        })
    except Exception:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
def cleanup_all():
    try:
        s.aria2.purgeDownloadResult()
        # Also clear uploading tasks?
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"🔑 API KEY: {API_KEY}")
    print(f"{'='*50}\n")
    log("info", "startup", f"Backend starting with API Key protection")
    app.run(port=5000)
