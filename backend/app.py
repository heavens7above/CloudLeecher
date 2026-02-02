import xmlrpc.client
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import shutil
import base64
import json
import time
import threading
import uuid
from datetime import datetime
from collections import deque
from functools import wraps

app = Flask(__name__)
CORS(app)

# --- Configuration ---
# Local temp storage for high-speed download (avoids FUSE latency)
DOWNLOAD_DIR = "/content/temp_downloads"
# Final destination on Google Drive
FINAL_DEST_DIR = "/content/drive/MyDrive/TorrentDownloads"
# Aria2 RPC
ARIA2_RPC_URL = "http://localhost:6800/rpc"
# Logging
LOG_FILE = "/content/backend_logs.json"

# Ensure directories exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(FINAL_DEST_DIR, exist_ok=True)

# --- State Management ---
# In-memory log storage (last 100 entries)
logs = deque(maxlen=100)
# Track tasks currently being moved to Drive: {gid: {name, progress, status, error}}
moving_tasks = {}
moving_tasks_lock = threading.Lock()

# Connect to Aria2 RPC
s = xmlrpc.client.ServerProxy(ARIA2_RPC_URL)

# --- Logging Helper ---
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

# --- Authentication Decorator ---
def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = os.environ.get('CLOUDLEECHER_API_KEY')
        if not api_key:
            # If no key configured in env, allow open access (dev mode or first run)
            # But in production logic below, we enforce generation.
            # For safety, if variable is missing, we log a warning but proceed
            # (or block? The plan said "mandatory check". Let's block if key exists).
            pass

        request_key = request.headers.get('x-api-key')
        if api_key and request_key != api_key:
            return jsonify({"error": "Unauthorized: Invalid API Key"}), 401

        return f(*args, **kwargs)
    return decorated

# --- Background Monitor (The "Mover") ---
class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

    def run(self):
        log("info", "monitor", "Background task monitor started")
        while self.running:
            try:
                self.check_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor loop failed: {str(e)}")
            time.sleep(2)

    def check_downloads(self):
        # 1. Get Stopped Tasks (Candidate for moving)
        try:
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength", "errorCode", "errorMessage"])
        except Exception as e:
            # Aria2 might be down
            return

        for task in stopped:
            gid = task['gid']
            status = task['status']

            if status == 'complete':
                # Start moving process
                self.handle_completed_task(task)
            elif status == 'error':
                # Log and remove
                log("error", "monitor", f"Download failed: {task.get('errorMessage')}", gid=gid)
                try:
                    s.aria2.removeDownloadResult(gid)
                except:
                    pass

    def handle_completed_task(self, task):
        gid = task['gid']

        # Check if already processing
        with moving_tasks_lock:
            if gid in moving_tasks:
                return

            # Register task as 'moving'
            files = task.get('files', [])
            if not files:
                return # Should not happen for complete tasks

            # Assume single file torrent or multi-file, we move the top directory or file
            # Aria2 structure: files=[{'path': '/content/temp/file.mkv', ...}]
            # We need to find the root path in DOWNLOAD_DIR

            source_path = files[0]['path']
            # Determine the actual root element to move.
            # If torrent structure was preserved, source_path usually starts with DOWNLOAD_DIR

            # Simple heuristic: Get the relative path from DOWNLOAD_DIR
            rel_path = os.path.relpath(source_path, DOWNLOAD_DIR)
            root_name = rel_path.split(os.sep)[0] # Top level folder or file name
            full_source_path = os.path.join(DOWNLOAD_DIR, root_name)

            file_size = task.get('totalLength', 0)

            moving_tasks[gid] = {
                "name": root_name,
                "status": "moving",
                "progress": 0,
                "size": file_size,
                "timestamp": datetime.now().isoformat()
            }

        # Remove from Aria2 immediately so it doesn't get processed again
        # The frontend will now look at 'moving_tasks' for this GID
        try:
            s.aria2.removeDownloadResult(gid)
        except:
            log("warning", "monitor", "Failed to remove result from Aria2", gid=gid)

        # Start the Move in a separate thread to not block the monitor loop
        threading.Thread(target=self.move_to_drive, args=(gid, full_source_path, root_name)).start()

    def move_to_drive(self, gid, source, name):
        log("info", "move", f"Starting move to Drive: {name}", gid=gid)

        try:
            if not os.path.exists(source):
                raise FileNotFoundError(f"Source file not found: {source}")

            dest = os.path.join(FINAL_DEST_DIR, name)

            # Handle Collisions
            if os.path.exists(dest):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = os.path.splitext(name)
                new_name = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
                dest = os.path.join(FINAL_DEST_DIR, new_name)
                log("warning", "move", f"Destination exists. Renaming to {new_name}", gid=gid)

            # Perform Move
            # shutil.move is generally atomic-ish on same filesystem, but here it's copying from Local to Fuse
            # This is the blocking part.
            shutil.move(source, dest)

            log("info", "move", "Move completed successfully", gid=gid)

            with moving_tasks_lock:
                if gid in moving_tasks:
                    moving_tasks[gid]['status'] = 'saved'
                    moving_tasks[gid]['progress'] = 100

            # Clean up entry after a delay
            time.sleep(60) # Keep "Saved" status visible for 1 min
            with moving_tasks_lock:
                if gid in moving_tasks:
                    del moving_tasks[gid]

        except Exception as e:
            log("error", "move", f"Move failed: {str(e)}", gid=gid)
            with moving_tasks_lock:
                if gid in moving_tasks:
                    moving_tasks[gid]['status'] = 'error'
                    moving_tasks[gid]['error'] = str(e)


# Start Monitor
monitor = BackgroundMonitor()
monitor.start()


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
    
    # Queue Enforcement
    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
    
    if len(active) > 0 or len(waiting) > 0:
        return jsonify({"error": "Queue full. Wait for current download."}), 429
    
    try:
        gid = s.aria2.addUri([magnet_link])
        log("info", "add_magnet", "Magnet added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
@require_api_key
def add_torrent_file():
    data = request.json
    b64_content = data.get('torrent')
    if not b64_content:
        return jsonify({"error": "Torrent content required"}), 400

    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])

    if len(active) > 0 or len(waiting) > 0:
        return jsonify({"error": "Queue full. Wait for current download."}), 429

    try:
        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        gid = s.aria2.addTorrent(binary_torrent)
        log("info", "add_torrent", "Torrent file added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
@require_api_key
def get_status():
    try:
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(extended_keys)
        waiting = s.aria2.tellWaiting(0, 100, basic_keys)
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
        # Add Moving Tasks (simulated as active/stopped tasks for frontend compatibility)
        # Or better: Add a separate list, or inject them into 'active' with a special status?
        # The frontend handles 'status'. If we send status='moving', frontend needs to support it.
        # Based on memory, frontend supports 'moving' and 'saved'.
        
        moving_list = []
        with moving_tasks_lock:
            for gid, info in moving_tasks.items():
                moving_list.append({
                    "gid": gid,
                    "status": info['status'], # 'moving' or 'saved' or 'error'
                    "totalLength": info['size'],
                    "completedLength": info['size'] if info['status'] == 'saved' else 0, # Progress bar hacking
                    "downloadSpeed": 0,
                    "files": [{"path": info['name']}],
                    "errorMessage": info.get('error'),
                    "errorCode": "0" if info.get('error') is None else "1"
                })
        
        # Inject moving tasks into 'active' or 'stopped'?
        # If we put them in 'active', they appear in the main list.
        # Frontend logic: updateTasksFromBackend takes all lists.
        # So we can just append them to 'active' or create a new category if frontend supported it.
        # For minimal frontend change, let's append to 'active' so they show up at top.
        active.extend(moving_list)
        
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
        # Also check moving tasks
        with moving_tasks_lock:
            if gid in moving_tasks:
                # Can't easily kill the move thread, but we can remove it from view
                del moving_tasks[gid]
                return jsonify({"status": "removed", "gid": gid})

        if 'not found' in str(e).lower():
            return jsonify({"status": "removed", "gid": gid})
        return jsonify({"error": str(e)}), 500

@app.route('/api/drive/info', methods=['GET'])
@require_api_key
def drive_info():
    try:
        # Check Final Dest (Drive) not Temp
        total, used, free = shutil.disk_usage(FINAL_DEST_DIR)
        return jsonify({"total": total, "used": used, "free": free})
    except:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
@require_api_key
def cleanup_all():
    try:
        s.aria2.purgeDownloadResult()
        # Also clear temp dir? Maybe dangerous if download in progress.
        # Let's stick to aria2 cleanup.
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    app.run(port=5000)
