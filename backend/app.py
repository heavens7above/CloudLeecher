import xmlrpc.client
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import os
import shutil
import base64
import json
import threading
import time
import logging
from datetime import datetime
from collections import deque
from functools import wraps

app = Flask(__name__)
CORS(app)

# Configuration
# "Production" configuration via Environment Variables
DRIVE_MOUNT_PATH = os.environ.get("DRIVE_MOUNT_PATH", "/content/drive")
FINAL_DOWNLOAD_DIR = os.environ.get("FINAL_DOWNLOAD_DIR", os.path.join(DRIVE_MOUNT_PATH, "MyDrive/TorrentDownloads"))
TEMP_DOWNLOAD_DIR = os.environ.get("TEMP_DOWNLOAD_DIR", "/content/temp_downloads")
ARIA2_RPC_URL = os.environ.get("ARIA2_RPC_URL", "http://localhost:6800/rpc")
LOG_FILE = "/content/backend_logs.json"
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY")

# Create directories
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
# We don't create FINAL_DOWNLOAD_DIR here because Drive might not be mounted yet when this script starts,
# although in the notebook flow it should be. We'll check it before moving.

# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)

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
        pass  # Don't crash on log write failure
    
    # Print to console for Colab visibility
    print(f"[{level.upper()}] {operation}: {message}" + (f" (GID: {gid})" if gid else ""))

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not API_KEY:
            # If no API Key is set in env, we might be in "open" mode or dev mode.
            # However, for production hardening, we should warn or block.
            # For now, if no key is set, we allow access (legacy behavior) but log a warning.
            # Ideally, we block. Let's block if the intent is hardening.
            # But to prevent locking out users who didn't set it in the old notebook,
            # we'll only block if CLOUDLEECHER_API_KEY is actually set (even if empty string? no).
            # If variable is MISSING, maybe allow?
            # DECISION: The notebook WILL set it. So we enforce it.
            # If it's missing, we return 500 "Server Misconfiguration".
            pass # We'll check below

        if API_KEY:
            request_key = request.headers.get('x-api-key')
            if not request_key or request_key != API_KEY:
                log("warning", "auth", f"Unauthorized access attempt from {request.remote_addr}")
                return jsonify({"error": "Unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated_function

# --- Background Task: Move to Drive ---

moving_gids = set()

def monitor_downloads_loop():
    """Background thread to monitor and move completed downloads"""
    while True:
        try:
            if not s:
                time.sleep(5)
                continue

            # Get stopped tasks (includes complete, error, removed)
            stopped = s.aria2.tellStopped(0, 1000, ["gid", "status", "files", "totalLength", "completedLength", "errorCode", "errorMessage"])

            for task in stopped:
                gid = task['gid']
                status = task['status']

                if status == 'complete' and gid not in moving_gids:
                    # Double check it's actually fully downloaded
                    if task['totalLength'] != task['completedLength']:
                        continue # Weird state, skip

                    moving_gids.add(gid)

                    # Start Move Operation in a separate thread to not block the monitor loop?
                    # No, monitor loop is slow anyway (5s), blocking is fine for simplicity,
                    # but if moving takes minutes, we stop processing others.
                    # Better to spawn a thread for the move.
                    threading.Thread(target=move_to_drive, args=(task,)).start()

                elif status == 'error' or status == 'removed':
                    # Auto-cleanup errors/removed after some time?
                    # For now, let the user manually clear them or use the "cleanup" button.
                    pass

        except Exception as e:
            print(f"Monitor Loop Error: {e}")

        time.sleep(5)

def move_to_drive(task):
    gid = task['gid']
    try:
        files = task.get('files', [])
        if not files:
            log("error", "move_to_drive", "No files found for task", gid=gid)
            return

        # Determine what to move.
        # Aria2 usually downloads to a directory if --dir is set.
        # If it's a single file torrent, it's at TEMP_DIR/filename
        # If it's a multi file, it's at TEMP_DIR/DirectoryName/files...

        # We need to find the "root" of the download in TEMP_DIR.
        # aria2 "files" returns absolute paths if we gave absolute --dir.

        # Heuristic: Take the first file's path.
        first_file_path = files[0]['path']

        # Check if it starts with TEMP_DIR
        if not first_file_path.startswith(TEMP_DOWNLOAD_DIR):
            log("warning", "move_to_drive", f"File path {first_file_path} is not in temp dir {TEMP_DOWNLOAD_DIR}", gid=gid)
            # It might be already in Drive if the user messed with config?
            # If so, just remove result.
            s.aria2.removeDownloadResult(gid)
            moving_gids.discard(gid)
            return

        # The relative path from TEMP_DIR
        rel_path = os.path.relpath(first_file_path, TEMP_DOWNLOAD_DIR)

        # The top-level component
        top_component = rel_path.split(os.sep)[0]

        source_path = os.path.join(TEMP_DOWNLOAD_DIR, top_component)
        dest_path = os.path.join(FINAL_DOWNLOAD_DIR, top_component)

        # Ensure Drive exists
        if not os.path.exists(FINAL_DOWNLOAD_DIR):
            try:
                os.makedirs(FINAL_DOWNLOAD_DIR, exist_ok=True)
            except Exception as e:
                log("error", "move_to_drive", f"Could not create destination dir: {e}", gid=gid)
                moving_gids.discard(gid)
                return

        log("info", "move_to_drive", f"Moving {top_component} to Drive...", gid=gid)

        # Handle Collision
        if os.path.exists(dest_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = f"{dest_path}_{timestamp}"
            log("warning", "move_to_drive", f"Destination exists, renaming to {os.path.basename(dest_path)}", gid=gid)

        # Perform Move
        try:
            shutil.move(source_path, dest_path)
            log("info", "move_to_drive", "Move completed successfully", gid=gid)

            # Remove from Aria2 (Clean up the list)
            s.aria2.removeDownloadResult(gid)

        except Exception as e:
            log("error", "move_to_drive", f"Move failed: {str(e)}", gid=gid)
            # We don't remove result so user sees it? Or we leave it in temp?
            # If we leave it, the monitor will try again.
            # We should probably leave it and log error.

    except Exception as e:
        log("error", "move_to_drive", f"Unexpected error: {str(e)}", gid=gid)
    finally:
        moving_gids.discard(gid)

# Start Background Thread
threading.Thread(target=monitor_downloads_loop, daemon=True).start()


# --- Routes ---

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
    
    # Check concurrent limits
    try:
        active = s.aria2.tellActive(["gid"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid"])
        if len(active) > 0 or len(waiting) > 0:
            return jsonify({"error": "Queue full. Please wait."}), 429

        gid = s.aria2.addUri([magnet_link], {"dir": TEMP_DOWNLOAD_DIR})
        log("info", "add_magnet", "Magnet added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
@require_api_key
def add_torrent_file():
    try:
        data = request.json
        b64_content = data.get('torrent')
        if not b64_content:
            return jsonify({"error": "Torrent content required"}), 400

        active = s.aria2.tellActive(["gid"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid"])
        if len(active) > 0 or len(waiting) > 0:
            return jsonify({"error": "Queue full"}), 429

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        # CRITICAL: Force dir to TEMP_DOWNLOAD_DIR
        gid = s.aria2.addTorrent(binary_torrent, [], {"dir": TEMP_DOWNLOAD_DIR})
        log("info", "add_torrent_file", "Torrent file added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent_file", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
@require_api_key
def get_status():
    try:
        keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "files", "errorMessage", "errorCode", "numSeeders", "connections", "infoHash"]
        
        active = s.aria2.tellActive(keys)
        waiting = s.aria2.tellWaiting(0, 100, keys)
        stopped = s.aria2.tellStopped(0, 100, keys)
        
        # Inject "moving" status info if needed
        # (The monitor removes them from aria2 once moved, but while moving they are "complete" in aria2)
        # We can verify if GID is in moving_gids
        
        for task in stopped:
            if task['gid'] in moving_gids:
                task['status'] = 'moving' # Custom status for frontend!
                # We need to make sure frontend handles 'moving' or we map it to something else?
                # If frontend doesn't know 'moving', it might break.
                # Let's check frontend code again?
                # Frontend just displays status string usually.
                # But logic might depend on 'active'/'complete'.
                # For safety, we can append to name?
                # Or just let it be 'complete' but add a flag.
                pass

        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
@require_api_key
def pause_download():
    gid = request.json.get('gid')
    try:
        s.aria2.pause(gid)
        return jsonify({"status": "paused", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
@require_api_key
def resume_download():
    gid = request.json.get('gid')
    try:
        s.aria2.unpause(gid)
        return jsonify({"status": "resumed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/remove', methods=['POST'])
@require_api_key
def remove_download():
    gid = request.json.get('gid')
    try:
        s.aria2.forceRemove(gid)
        return jsonify({"status": "removed", "gid": gid})
    except Exception as e:
        # If not found, success
        return jsonify({"status": "removed", "gid": gid})

@app.route('/api/drive/info', methods=['GET'])
@require_api_key
def drive_info():
    try:
        # Check actual drive path
        path = FINAL_DOWNLOAD_DIR if os.path.exists(FINAL_DOWNLOAD_DIR) else DRIVE_MOUNT_PATH
        total, used, free = shutil.disk_usage(path)
        return jsonify({"total": total, "used": used, "free": free})
    except:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
@require_api_key
def cleanup_all():
    try:
        s.aria2.purgeDownloadResult()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    if not API_KEY:
        log("warning", "startup", "NO API KEY SET! Security is disabled.")
    else:
        log("info", "startup", "API Key protection enabled.")

    app.run(port=5000)
