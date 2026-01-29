import xmlrpc.client
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import os
import shutil
import base64
import json
import threading
import time
import secrets
from datetime import datetime
from collections import deque

app = Flask(__name__)
CORS(app)

# Configuration
# Download to local temp first to avoid FUSE issues
DOWNLOAD_DIR = "/content/temp_downloads"
# Final destination on Google Drive
FINAL_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# Ensure directories exist
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
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

# --- Authentication ---
@app.before_request
def check_api_key():
    # Allow health check without auth
    if request.endpoint == 'health' or request.method == 'OPTIONS':
        return

    api_key = os.environ.get('CLOUDLEECHER_API_KEY')
    if not api_key:
        # If no key configured, allow (dev mode) or block?
        # For security, we should probably generate one if missing, but for now let's assume it's passed.
        # If the environment variable is NOT set, we log a warning but maybe allow it?
        # The prompt says "Generate it if missing".
        pass
    else:
        client_key = request.headers.get('x-api-key')
        if client_key != api_key:
            abort(401, description="Invalid API Key")

# --- Background Monitor ---
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
                log("error", "monitor", f"Monitor loop failed: {str(e)}")
            time.sleep(5)

    def check_downloads(self):
        # We need to find tasks that are 'complete' but haven't been moved yet.
        # Aria2 keeps them in 'stopped' list with status='complete'.
        try:
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "bittorrent"])

            for task in stopped:
                if task['status'] == 'complete':
                    self.process_completed_task(task)
        except Exception as e:
            # log("error", "monitor", f"Failed to query aria2: {str(e)}")
            pass

    def process_completed_task(self, task):
        gid = task['gid']
        files = task.get('files', [])

        # Check if already processed (custom logic or check if file exists in source)
        # Simple heuristic: If the file exists in DOWNLOAD_DIR, move it.

        for file_info in files:
            path = file_info['path']
            if not path.startswith(DOWNLOAD_DIR):
                continue # Already moved or invalid path

            if not os.path.exists(path):
                # File not found at source, maybe already moved?
                continue

            # It's here! Let's move it.
            # Determine relative path to maintain structure if it's a directory
            rel_path = os.path.relpath(path, DOWNLOAD_DIR)
            dest_path = os.path.join(FINAL_DIR, rel_path)

            # Handle collisions
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(dest_path)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_path = f"{base}_{timestamp}{ext}"

            # Ensure dest dir exists
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            try:
                log("info", "mover", f"Moving {rel_path} to Drive...", gid=gid)
                shutil.move(path, dest_path)
                log("info", "mover", f"Moved to {dest_path}", gid=gid)

                # Update Aria2 to remove this task so we don't process it again?
                # Or we can leave it. If we leave it, the path check `os.path.exists(path)` will fail next time, which is what we want.
                # But it's better to remove the result to keep the list clean.
                s.aria2.removeDownloadResult(gid)
                log("info", "monitor", "Task removed from queue after move", gid=gid)

            except Exception as e:
                log("error", "mover", f"Failed to move file: {str(e)}", gid=gid)

# Start monitor
monitor = BackgroundMonitor()
# monitor.start() # Will start in __main__

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "CloudLeecher-Backend", "auth": bool(os.environ.get('CLOUDLEECHER_API_KEY'))})

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
    
    # BACKEND QUEUE ENFORCEMENT: Only allow one active download
    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
    
    if len(active) > 0 or len(waiting) > 0:
        log("warning", "add_magnet", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
        return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
    
    try:
        # options = {"dir": DOWNLOAD_DIR} # Force temp dir
        # We set default dir in aria2 config, but better to be explicit if needed.
        # Actually aria2 daemon is started with --dir=DOWNLOAD_DIR.
        # Since we changed DOWNLOAD_DIR at top of file, we need to ensure aria2 uses it.
        # But aria2 is started externally.
        # CRITICAL: app.py uses DOWNLOAD_DIR constant, but CloudLeecher.ipynb starts aria2.
        # We must ensure CloudLeecher.ipynb starts aria2 with the NEW DOWNLOAD_DIR.
        # For now, let's explicitly pass dir here too.
        gid = s.aria2.addUri([magnet_link], {"dir": DOWNLOAD_DIR})
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

        # BACKEND QUEUE ENFORCEMENT: Only allow one active download
        active = s.aria2.tellActive(["gid", "status"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
        
        if len(active) > 0 or len(waiting) > 0:
            log("warning", "add_torrent_file", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
            return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        log("info", "add_torrent_file", f"Received torrent file ({len(raw_bytes)} bytes), adding to aria2...")
        gid = s.aria2.addTorrent(binary_torrent, [], {"dir": DOWNLOAD_DIR})
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
def get_status():
    try:
        # Use safe keys for non-active tasks to avoid API errors/empty responses
        basic_keys = ["gid", "status", "totalLength", "completedLength", "downloadSpeed", "uploadSpeed", "dir", "files", "errorMessage", "errorCode", "followedBy", "following"]
        extended_keys = basic_keys + ["numSeeders", "connections", "infoHash", "bittorrent"]
        
        active = s.aria2.tellActive(extended_keys)
        waiting = s.aria2.tellWaiting(0, 100, basic_keys)
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
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
            # log_msg = f"Currently tracking {len(all_gids)} tasks"
            # if gid_transitions:
            #     log_msg += f" | Transitions: {', '.join(gid_transitions)}"
            # log("info", "status_poll", log_msg, extra={"gids": all_gids})
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
            # Remove error tasks (keep completed ones for the mover to find!)
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
    
    # Ensure API Key is present (generate if missing and warn)
    if not os.environ.get('CLOUDLEECHER_API_KEY'):
        generated_key = secrets.token_hex(16)
        os.environ['CLOUDLEECHER_API_KEY'] = generated_key
        log("warning", "startup", f"No API Key found. Generated temporary key: {generated_key}")
        print(f"\n🔑 AUTOMATICALLY GENERATED API KEY: {generated_key}\n")

    # Clean up any existing stalled tasks on startup
    log("info", "startup", "Cleaning up stalled tasks from previous session...")
    purge_stalled_downloads()
    
    # Start Background Monitor
    monitor.start()

    app.run(port=5000, threaded=True)
