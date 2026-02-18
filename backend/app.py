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
import threading
import time
import secrets
from functools import wraps

app = Flask(__name__)
CORS(app)

# Configuration
# Use a local temporary directory for downloading to avoid FUSE issues
TEMP_DOWNLOAD_DIR = "/content/temp_downloads"
# Final destination on Google Drive
FINAL_DIR = "/content/drive/MyDrive/TorrentDownloads"

# --- Configuration ---
# Use a local path for high-speed download (SSD), then move to Drive
TEMP_DOWNLOAD_DIR = "/content/temp_downloads"
FINAL_DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY")

# Ensure directories exist
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(FINAL_DIR, exist_ok=True)

# Authentication
API_KEY = os.environ.get('CLOUDLEECHER_API_KEY')
if not API_KEY:
    # If not provided via env, generate one (fallback)
    API_KEY = secrets.token_hex(16)
    print(f"\n{'='*50}\nGenerated API Key: {API_KEY}\n{'='*50}\n")
else:
    print(f"\n{'='*50}\nUsing Configured API Key: {API_KEY}\n{'='*50}\n")

# Create directories
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
# We don't create FINAL_DOWNLOAD_DIR here because Drive might not be mounted yet when this script starts,
# although in the notebook flow it should be. We'll check it before moving.

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
# Retry connection in case aria2 is slow to start
s = None
for i in range(5):
    try:
        s = xmlrpc.client.ServerProxy(ARIA2_RPC_URL)
        s.aria2.getVersion()
        print("Connected to Aria2 RPC")
        break
    except Exception as e:
        print(f"Waiting for Aria2... ({i+1}/5)")
        time.sleep(2)

if not s:
    print("FATAL: Could not connect to Aria2 RPC")

# --- Helpers ---

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
    
    # Print to console
    print(f"[{level.upper()}] {operation}: {message}" + (f" (GID: {gid})" if gid else ""))

def check_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        request_key = request.headers.get('x-api-key')
        if not request_key or request_key != API_KEY:
            log("warning", "auth", "Unauthorized access attempt")
            return jsonify({"error": "Unauthorized: Invalid or missing API Key"}), 401
        return f(*args, **kwargs)
    return decorated_function

class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.stopped = False

    def run(self):
        log("info", "monitor", "Background monitor started")
        while not self.stopped:
            try:
                self.check_completed_downloads()
            except Exception as e:
                pass # Silent fail (e.g. aria2 not ready yet)
            time.sleep(5)

    def check_completed_downloads(self):
        try:
            # Get stopped tasks (includes complete, error, removed)
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "bittorrent", "totalLength", "errorCode"])

            for task in stopped:
                status = task['status']
                gid = task['gid']

                if status == 'complete':
                    self.handle_complete_task(task)
                elif status == 'error':
                     # Log error and remove
                     err_code = task.get('errorCode', 'unknown')
                     log("error", "download", f"Task failed with error code {err_code}", gid=gid)
                     try: s.aria2.removeDownloadResult(gid)
                     except: pass
                elif status == 'removed':
                     try: s.aria2.removeDownloadResult(gid)
                     except: pass

        except Exception as e:
            pass

    def handle_complete_task(self, task):
        gid = task['gid']
        files = task.get('files', [])

        if not files:
            try: s.aria2.removeDownloadResult(gid)
            except: pass
            return

        # Try to find the root file or directory
        bt_name = task.get('bittorrent', {}).get('info', {}).get('name')

        source_path = None

        # Strategy 1: Look for the name provided in metadata
        if bt_name:
             possible_path = os.path.join(TEMP_DOWNLOAD_DIR, bt_name)
             if os.path.exists(possible_path):
                 source_path = possible_path

        # Strategy 2: Use the first file path
        if not source_path and files:
            first_file_path = files[0]['path']
            # If the path starts with TEMP_DOWNLOAD_DIR, great
            if os.path.exists(first_file_path):
                # If it's a multi-file torrent, first_file_path is deep inside
                # We want the top-level directory.
                rel_path = os.path.relpath(first_file_path, TEMP_DOWNLOAD_DIR)
                top_level = rel_path.split(os.sep)[0]
                possible_path = os.path.join(TEMP_DOWNLOAD_DIR, top_level)
                if os.path.exists(possible_path):
                    source_path = possible_path

        if not source_path:
             log("error", "move", "Could not locate downloaded files", gid=gid)
             # Don't remove result so we can debug? Or remove to avoid loop?
             # Remove it to avoid infinite loop
             try: s.aria2.removeDownloadResult(gid)
             except: pass
             return

        dest_path = os.path.join(FINAL_DIR, os.path.basename(source_path))

        # Handle collision
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(os.path.basename(source_path))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = os.path.join(FINAL_DIR, f"{base}_{timestamp}{ext}")

        log("info", "move", f"Moving {os.path.basename(source_path)} to Drive...", gid=gid)

        try:
            shutil.move(source_path, dest_path)
            log("info", "move", f"Move successful: {os.path.basename(dest_path)}", gid=gid)
            try: s.aria2.removeDownloadResult(gid)
            except: pass
        except Exception as e:
            log("error", "move", f"Move failed: {str(e)}", gid=gid)
            # If move failed (e.g. Drive full), we leave the task in 'stopped' state
            # but 'tellStopped' returns it again.
            # To avoid retry loop spam, we might need to blacklist it in memory
            # or just log error.
            # For now, we leave it.
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
@check_auth
def get_logs():
    try:
        return jsonify({"logs": list(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/magnet', methods=['POST'])
@check_auth
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
    
    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
    
    if len(active) > 0 or len(waiting) > 0:
        log("warning", "add_magnet", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
        return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
    
    try:
        # Note: DOWNLOAD_DIR is set in aria2c startup args, but addUri inherits it.
        # We don't need to specify dir here unless we want to override.
        gid = s.aria2.addUri([magnet_link])
        log("info", "add_magnet", "Magnet link added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
@check_auth
def add_torrent_file():
    try:
        data = request.json
        b64_content = data.get('torrent')
        if not b64_content:
            log("error", "add_torrent_file", "Torrent file content is required")
            return jsonify({"error": "Torrent file content is required"}), 400

        active = s.aria2.tellActive(["gid", "status"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
        
        if len(active) > 0 or len(waiting) > 0:
            log("warning", "add_torrent_file", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
            return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
@require_api_key
def add_torrent_file():
    data = request.json
    b64_content = data.get('torrent')
    if not b64_content:
        return jsonify({"error": "Torrent content required"}), 400

    try:
        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        gid = s.aria2.addTorrent(binary_torrent)
        log("info", "add_torrent_file", "Torrent file added successfully, downloading metadata...", gid=gid)
        
        try:
            status = s.aria2.tellStatus(gid, ["gid", "status", "files", "bittorrent"])
            torrent_name = status.get('bittorrent', {}).get('info', {}).get('name', 'Unknown')
            log("info", "add_torrent_file", f"Torrent name: {torrent_name}", gid=gid, extra={"status": status.get('status')})
        except:
            pass
        
        log("info", "add_torrent_file", "Torrent file added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent_file", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
@check_auth
def get_status():
    try:
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
@require_api_key
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
@check_auth
@require_api_key
def pause_download():
    gid = request.json.get('gid')
    try:
        s.aria2.pause(gid)
        return jsonify({"status": "paused", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
@check_auth
@require_api_key
def resume_download():
    gid = request.json.get('gid')
    try:
        s.aria2.unpause(gid)
        return jsonify({"status": "resumed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/remove', methods=['POST'])
@check_auth
@require_api_key
def remove_download():
    gid = request.json.get('gid')
    try:
        s.aria2.forceRemove(gid)
        return jsonify({"status": "removed", "gid": gid})
    except xmlrpc.client.Fault as e:
        if 'not found' in str(e).lower():
            log("info", "remove_download", "GID not found (already removed)", gid=request.json.get('gid'))
            return jsonify({"status": "removed", "gid": request.json.get('gid')})
        else:
            log("error", "remove_download", f"Aria2 error: {str(e)}", gid=request.json.get('gid'))
            return jsonify({"error": str(e)}), 500
    except Exception as e:
        # If not found, it's fine
        return jsonify({"status": "removed", "gid": gid})

@app.route('/api/drive/info', methods=['GET'])
@check_auth
def drive_info():
    try:
        total, used, free = shutil.disk_usage(FINAL_DIR)
@require_api_key
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
@check_auth
@require_api_key
def cleanup_all():
    try:
        active = s.aria2.tellActive(["gid"])
        waiting = s.aria2.tellWaiting(0, 9999, ["gid"])
        stopped = s.aria2.tellStopped(0, 9999, ["gid"])
        
        removed_count = 0
        
        for task in active + waiting:
            try:
                s.aria2.forceRemove(task['gid'])
                removed_count += 1
            except:
                pass
        
        try:
            s.aria2.purgeDownloadResult()
            removed_count += len(stopped)
        except:
            pass
        
        log("info", "cleanup_all", f"Cleaned up {removed_count} tasks")
        return jsonify({"status": "success", "removed": removed_count})
        s.aria2.purgeDownloadResult()
        # Also clear uploading tasks?
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    
    # Start background monitor
    monitor = BackgroundMonitor()
    monitor.start()
    
    print(f"\n{'='*50}")
    print(f"🔑 API KEY: {API_KEY}")
    print(f"{'='*50}\n")
    log("info", "startup", f"Backend starting with API Key protection")
    app.run(port=5000)
