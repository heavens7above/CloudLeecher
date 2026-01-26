import xmlrpc.client
from flask import Flask, request, jsonify, abort
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
from functools import wraps

app = Flask(__name__)
CORS(app)

# Configuration
# Use a local temporary directory for downloading to avoid FUSE issues
TEMP_DOWNLOAD_DIR = "/content/temp_downloads"
# Final destination on Google Drive
FINAL_DIR = "/content/drive/MyDrive/TorrentDownloads"

ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

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

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "CloudLeecher-Backend"})

@app.route('/api/logs', methods=['GET'])
@check_auth
def get_logs():
    try:
        return jsonify({"logs": list(logs)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/magnet', methods=['POST'])
@check_auth
def add_magnet():
    data = request.json
    magnet_link = data.get('magnet')
    if not magnet_link:
        log("error", "add_magnet", "Magnet link is required")
        return jsonify({"error": "Magnet link is required"}), 400
    
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

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        log("info", "add_torrent_file", f"Received torrent file ({len(raw_bytes)} bytes), adding to aria2...")
        gid = s.aria2.addTorrent(binary_torrent)
        log("info", "add_torrent_file", "Torrent file added successfully, downloading metadata...", gid=gid)
        
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
@check_auth
def get_status():
    try:
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(extended_keys)
        waiting = s.aria2.tellWaiting(0, 100, basic_keys)
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        log("error", "get_status", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
@check_auth
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
@check_auth
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
@check_auth
def remove_download():
    try:
        gid = request.json.get('gid')
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
@check_auth
def drive_info():
    try:
        total, used, free = shutil.disk_usage(FINAL_DIR)
        return jsonify({
            "total": total,
            "used": used,
            "free": free
        })
    except Exception as e:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
@check_auth
def cleanup_all():
    """Nuclear option: Remove ALL tasks from aria2 and start fresh"""
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
    except Exception as e:
        log("error", "cleanup_all", f"Failed: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    
    # Start background monitor
    monitor = BackgroundMonitor()
    monitor.start()
    
    app.run(port=5000)
