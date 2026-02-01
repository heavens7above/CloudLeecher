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
DRIVE_DIR = "/content/drive/MyDrive/TorrentDownloads"
TEMP_DIR = "/content/temp_downloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"
HISTORY_FILE = "/content/download_history.json"

# Ensure temp dir exists
os.makedirs(TEMP_DIR, exist_ok=True)

# In-memory log storage
logs = deque(maxlen=200)

# Connect to Aria2 RPC
s = xmlrpc.client.ServerProxy(ARIA2_RPC_URL)

def log(level, operation, message, gid=None, extra=None):
    """Add entry to log with timestamp and details"""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "operation": operation,
        "message": message,
        "gid": gid,
        "extra": extra
    }
    logs.append(entry)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except:
        pass
    print(f"[{level.upper()}] {operation}: {message}" + (f" (GID: {gid})" if gid else ""))

# --- Authentication ---
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        server_key = os.environ.get('CLOUDLEECHER_API_KEY')
        if not server_key:
            return jsonify({"error": "Server configuration error: No API Key set"}), 500

        client_key = request.headers.get('x-api-key')
        if not client_key or client_key != server_key:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# --- Task History Management ---
class TaskHistory:
    def __init__(self):
        self.tasks = {} # gid -> task_dict
        self.load()

    def load(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.tasks = {t['gid']: t for t in data}
                    else:
                        self.tasks = data
            except Exception as e:
                log("error", "history_load", f"Failed to load history: {e}")

    def save(self):
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.tasks, f)
        except Exception as e:
            log("error", "history_save", f"Failed to save history: {e}")

    def add_or_update(self, task):
        self.tasks[task['gid']] = task
        self.save()

    def get_all(self):
        return list(self.tasks.values())

    def remove(self, gid):
        if gid in self.tasks:
            del self.tasks[gid]
            self.save()

history = TaskHistory()

# --- Background Monitor ---
class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.stopped_event = threading.Event()

    def run(self):
        log("info", "monitor", "Background monitor started")
        while not self.stopped_event.is_set():
            try:
                self.check_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor loop error: {e}")
            time.sleep(2)

    def check_downloads(self):
        try:
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "totalLength", "completedLength", "errorMessage", "errorCode", "infoHash", "bittorrent"])

            for task in stopped:
                gid = task['gid']
                status = task['status']

                if status == 'complete':
                    files = task.get('files', [])
                    if not files:
                        continue
                    self.process_completed_task(task)

        except Exception as e:
            pass

    def process_completed_task(self, task):
        gid = task['gid']

        if gid in history.tasks and history.tasks[gid].get('status') in ['moving', 'saved']:
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass
            return

        task['status'] = 'moving'
        history.add_or_update(task)

        log("info", "mover", "Starting move to Drive", gid=gid)

        try:
            source_files = task['files']
            if not source_files:
                raise Exception("No files found in task")

            first_file_path = source_files[0]['path']

            # Since we forced download to TEMP_DIR, paths should be correct.
            # But double check if aria2 returns absolute path including TEMP_DIR

            torrent_name = task.get('bittorrent', {}).get('info', {}).get('name')
            if not torrent_name:
                torrent_name = os.path.basename(first_file_path)

            source_path = os.path.join(TEMP_DIR, torrent_name)
            dest_path = os.path.join(DRIVE_DIR, torrent_name)

            if not os.path.exists(source_path):
                if os.path.exists(first_file_path):
                    source_path = first_file_path
                    dest_path = os.path.join(DRIVE_DIR, os.path.basename(source_path))
                else:
                    raise Exception(f"Source path not found: {source_path}")

            if os.path.exists(dest_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name, ext = os.path.splitext(torrent_name)
                new_name = f"{name}_{timestamp}{ext}"
                dest_path = os.path.join(DRIVE_DIR, new_name)
                log("warning", "mover", f"Destination exists, renaming to {new_name}", gid=gid)

            log("info", "mover", f"Moving {source_path} to {dest_path}", gid=gid)
            shutil.move(source_path, dest_path)

            task['status'] = 'saved'
            task['dest_path'] = dest_path
            history.add_or_update(task)
            log("info", "mover", "Move complete", gid=gid)

            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass

        except Exception as e:
            log("error", "mover", f"Move failed: {e}", gid=gid)
            task['status'] = 'error'
            task['errorMessage'] = f"Move failed: {str(e)}"
            history.add_or_update(task)
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass

monitor = BackgroundMonitor()

# --- Routes ---

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "CloudLeecher-Backend"})

@app.route('/api/logs', methods=['GET'])
@require_auth
def get_logs():
    return jsonify({"logs": list(logs)})

@app.route('/api/download/magnet', methods=['POST'])
@require_auth
def add_magnet():
    data = request.json
    magnet_link = data.get('magnet')
    if not magnet_link:
        return jsonify({"error": "Magnet link is required"}), 400
    
    active = s.aria2.tellActive(["gid"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid"])
    if len(active) > 0 or len(waiting) > 0:
        return jsonify({"error": "Queue full. Wait for current download."}), 429
    
    try:
        # Force download to TEMP_DIR
        gid = s.aria2.addUri([magnet_link], {"dir": TEMP_DIR})
        log("info", "add_magnet", "Magnet added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_magnet", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/download/file', methods=['POST'])
@require_auth
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
        
        # Force download to TEMP_DIR
        # aria2.addTorrent(torrent, [uris], [options])
        gid = s.aria2.addTorrent(binary_torrent, [], {"dir": TEMP_DIR})
        log("info", "add_torrent", "Torrent file added", gid=gid)
        return jsonify({"status": "success", "gid": gid})
    except Exception as e:
        log("error", "add_torrent", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
@require_auth
def get_status():
    try:
        keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(keys)
        waiting = s.aria2.tellWaiting(0, 100, keys)
        stopped = s.aria2.tellStopped(0, 100, keys)
        
        history_tasks = history.get_all()
        current_gids = set(t['gid'] for t in active + waiting + stopped)
        
        final_stopped = list(stopped)
        for h_task in history_tasks:
            if h_task['gid'] not in current_gids:
                final_stopped.append(h_task)

        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": final_stopped
        })
    except Exception as e:
        log("error", "status", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/pause', methods=['POST'])
@require_auth
def pause_download():
    gid = request.json.get('gid')
    try:
        s.aria2.pause(gid)
        return jsonify({"status": "paused", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/resume', methods=['POST'])
@require_auth
def resume_download():
    gid = request.json.get('gid')
    try:
        s.aria2.unpause(gid)
        return jsonify({"status": "resumed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/control/remove', methods=['POST'])
@require_auth
def remove_download():
    gid = request.json.get('gid')
    try:
        try:
            s.aria2.forceRemove(gid)
        except:
            pass
        try:
            s.aria2.removeDownloadResult(gid)
        except:
            pass

        history.remove(gid)

        log("info", "remove", "Task removed", gid=gid)
        return jsonify({"status": "removed", "gid": gid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/drive/info', methods=['GET'])
@require_auth
def drive_info():
    try:
        total, used, free = shutil.disk_usage(DRIVE_DIR)
        return jsonify({"total": total, "used": used, "free": free})
    except:
        return jsonify({"total": 0, "used": 0, "free": 0})

@app.route('/api/cleanup', methods=['POST'])
@require_auth
def cleanup_all():
    try:
        s.aria2.purgeDownloadResult()
        history.tasks = {}
        history.save()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    monitor.start()
    app.run(port=5000)
