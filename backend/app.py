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

app = Flask(__name__)
CORS(app)

# Configuration
# Use a local temp directory for Aria2 to avoid FUSE locking/slowness
DOWNLOAD_DIR = "/content/temp_downloads"
# Final destination on Google Drive
FINAL_DEST_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# Ensure directories exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(FINAL_DEST_DIR, exist_ok=True)

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
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY")

@app.before_request
def check_api_key():
    if request.method == "OPTIONS":
        return
    if request.endpoint == "health":
        return

    key = request.headers.get("x-api-key")
    if API_KEY and key != API_KEY:
        log("warning", "auth", "Unauthorized access attempt")
        return jsonify({"error": "Unauthorized"}), 401

# --- Background Monitor ---
class BackgroundMonitor(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        # Track tasks that are currently being moved or have completed moving
        # Key: GID, Value: {status: 'moving'|'saved', timestamp: ...}
        self.history = {}

    def run(self):
        log("info", "monitor", "Background monitor started")
        while self.running:
            try:
                self.check_downloads()
            except Exception as e:
                log("error", "monitor", f"Monitor loop error: {str(e)}")
            time.sleep(5)

    def check_downloads(self):
        try:
            # Check stopped tasks for completion
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "errorCode"])

            for task in stopped:
                gid = task['gid']

                # Skip if already processed/processing
                if gid in self.history:
                    continue

                if task['status'] == 'complete':
                    self.process_completed_task(task)
                elif task['status'] == 'error':
                    # Log error and maybe cleanup
                    log("error", "monitor", f"Task failed: {task.get('errorCode')}", gid=gid)
                    # We leave it in aria2 so user can see the error, or move to history?
                    # For now, let it sit in aria2 stopped list.

        except Exception as e:
            log("error", "monitor", f"Check downloads failed: {str(e)}")

    def process_completed_task(self, task):
        gid = task['gid']
        files = task['files']

        log("info", "monitor", "Processing completed task...", gid=gid)
        self.history[gid] = {'status': 'moving', 'timestamp': datetime.now().isoformat()}

        try:
            moved_files = []
            for f in files:
                path = f['path']
                if not path.startswith(DOWNLOAD_DIR):
                    continue

                # Determine relative path to maintain structure
                rel_path = os.path.relpath(path, DOWNLOAD_DIR)
                dest_path = os.path.join(FINAL_DEST_DIR, rel_path)

                # Create dest dir
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                # Handle collision
                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(dest_path)
                    dest_path = f"{base}_{int(time.time())}{ext}"

                log("info", "monitor", f"Moving {rel_path} to Drive...", gid=gid)
                shutil.move(path, dest_path)
                moved_files.append(dest_path)

            self.history[gid] = {
                'status': 'saved',
                'timestamp': datetime.now().isoformat(),
                'files': moved_files
            }
            log("info", "monitor", "Move complete. Removed from Aria2.", gid=gid)

            # Remove from Aria2 to keep it clean, since we track it in history now
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass

        except Exception as e:
            log("error", "monitor", f"Move failed: {str(e)}", gid=gid)
            self.history[gid] = {'status': 'error', 'errorMessage': str(e), 'timestamp': datetime.now().isoformat()}

monitor = BackgroundMonitor()
monitor.start()

# --- Routes ---

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
    
    # BACKEND QUEUE ENFORCEMENT
    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
    
    if len(active) > 0 or len(waiting) > 0:
        log("warning", "add_magnet", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
        return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
    
    try:
        # Add URI without specific dir option, relying on daemon startup config (which we set to DOWNLOAD_DIR)
        # OR explicitly set it here to be safe.
        options = {"dir": DOWNLOAD_DIR}
        gid = s.aria2.addUri([magnet_link], options)
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

        active = s.aria2.tellActive(["gid", "status"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
        
        if len(active) > 0 or len(waiting) > 0:
            log("warning", "add_torrent_file", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
            return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        log("info", "add_torrent_file", f"Received torrent file ({len(raw_bytes)} bytes), adding to aria2...")
        options = {"dir": DOWNLOAD_DIR}
        gid = s.aria2.addTorrent(binary_torrent, [], options)
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
def get_status():
    try:
        # Use safe keys for non-active tasks
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(extended_keys)
        waiting = s.aria2.tellWaiting(0, 100, basic_keys)
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
        # Inject our history tasks into 'stopped' so frontend sees them
        # Convert our simple history format to something resembling aria2 response
        history_tasks = []
        for gid, info in monitor.history.items():
            # Determine status for frontend
            # The frontend TaskList uses specific icons/colors.
            # 'moving' -> (we need to handle this in frontend, or map to something existing)
            # 'saved' -> (we need to handle this)

            # Construct a fake aria2 task object
            # We try to get data from the original stopped task if we can, but we might have lost it.
            # For now, minimal info.
            task_status = info['status'] # 'moving', 'saved', 'error'

            history_tasks.append({
                "gid": gid,
                "status": task_status,
                "totalLength": "0", # We lost size info if we didn't cache it, but maybe we don't care
                "completedLength": "0",
                "downloadSpeed": "0",
                "uploadSpeed": "0",
                "files": [{"path": f} for f in info.get('files', [])],
                "errorMessage": info.get('errorMessage')
            })

        # Merge history into stopped
        # Filter out any history GIDs that might still be in stopped (unlikely due to removeDownloadResult)
        stopped_gids = set(t['gid'] for t in stopped)
        for h_task in history_tasks:
            if h_task['gid'] not in stopped_gids:
                stopped.append(h_task)

        # Track GID transitions for debugging (existing logic)
        all_tasks = active + waiting + stopped
        all_gids = [t['gid'] for t in all_tasks]
        
        gid_transitions = []
        for task in all_tasks:
            if task.get('followedBy'):
                for followed_gid in task['followedBy']:
                    gid_transitions.append(f"{task['gid'][:8]} → {followed_gid[:8]}")
            
            if task.get('following'):
                # Check if we have history for the PARENT task
                pass

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

        # Check if it's in our history
        if gid in monitor.history:
            del monitor.history[gid]
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
def drive_info():
    try:
        # Check stats of the FINAL DESTINATION
        total, used, free = shutil.disk_usage(FINAL_DEST_DIR)
        return jsonify({
            "total": total,
            "used": used,
            "free": free
        })
    except Exception as e:
        # Fallback if drive not mounted
        return jsonify({"total": 0, "used": 0, "free": 0})

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

        # Clear history
        monitor.history.clear()
        
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
            # Only purge errors or explicitly removed tasks.
            # Completed tasks are handled by BackgroundMonitor now.
            if task['status'] in ['error', 'removed']:
                try:
                    s.aria2.removeDownloadResult(task['gid'])
                    purged += 1
                except:
                    pass
        
        if purged > 0:
            log("info", "auto_purge", f"Automatically purged {purged} failed tasks")
            
    except Exception as e:
        pass

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    
    # Clean up any existing stalled tasks on startup
    log("info", "startup", "Cleaning up stalled tasks from previous session...")
    purge_stalled_downloads()
    
    if not API_KEY:
        log("warning", "startup", "NO API KEY SET! Backend is insecure.")
    else:
        log("info", "startup", "API Key Authentication Enabled")

    app.run(port=5000)
