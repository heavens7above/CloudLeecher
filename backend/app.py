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

# --- Configuration ---
# Use a fast local directory for initial download
DOWNLOAD_DIR = "/content/temp_downloads"
# Use Google Drive for final storage
FINAL_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# API Key Security
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY")
if not API_KEY:
    # Generate a random key if not provided
    API_KEY = secrets.token_hex(16)
    print(f"\n{'='*60}")
    print(f"🔑 GENERATED API KEY: {API_KEY}")
    print(f"{'='*60}\n")

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

# --- Authentication Middleware ---
@app.before_request
def check_auth():
    if request.method == 'OPTIONS':
        return

    # Skip auth for health check
    if request.path == '/health':
        return

    key = request.headers.get('x-api-key')
    if key != API_KEY:
        abort(401, description="Invalid or missing API Key")

# --- Background Mover Thread ---
class BackgroundMover(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True

    def run(self):
        log("info", "mover_thread", "Background mover thread started")
        while self.running:
            try:
                self.check_and_move_files()
            except Exception as e:
                log("error", "mover_thread", f"Unexpected error: {str(e)}")
            time.sleep(5)

    def check_and_move_files(self):
        try:
            # Check for stopped tasks (complete or error)
            stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "errorCode", "errorMessage"])

            for task in stopped:
                gid = task['gid']
                status = task['status']

                if status == 'complete':
                    self.handle_complete(task)
                elif status == 'error':
                    self.handle_error(task)
                elif status == 'removed':
                    # just cleanup
                    try:
                        s.aria2.removeDownloadResult(gid)
                    except:
                        pass
        except Exception as e:
            # log("error", "mover_thread_check", f"Failed to query aria2: {str(e)}")
            pass

    def handle_complete(self, task):
        gid = task['gid']
        files = task['files']

        if not files:
            return

        # Usually torrents download to a single directory or file
        # The first file path usually gives the root structure
        source_path = files[0]['path']

        # If path is empty (metadata only?), skip
        if not source_path:
            return

        # Check if file exists in DOWNLOAD_DIR
        if not os.path.exists(source_path):
            log("warning", "mover_move", "Source file not found (already moved?)", gid=gid, extra={"path": source_path})
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass
            return

        # Determine the root file/folder to move
        # If it's a multi-file torrent, aria2 creates a directory.
        # We need to find the top-level element in DOWNLOAD_DIR that corresponds to this task.

        # Simple heuristic:
        # task['files'][0]['path'] looks like "/content/temp_downloads/MyTorrent/file.mkv"
        # We want to move "/content/temp_downloads/MyTorrent"

        rel_path = os.path.relpath(source_path, DOWNLOAD_DIR)
        top_level_name = rel_path.split(os.sep)[0]
        full_source_path = os.path.join(DOWNLOAD_DIR, top_level_name)

        dest_path = os.path.join(FINAL_DIR, top_level_name)

        # Handle collisions
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(top_level_name)
            timestamp = int(time.time())
            new_name = f"{base}_{timestamp}{ext}"
            dest_path = os.path.join(FINAL_DIR, new_name)
            log("info", "mover_collision", f"Destination exists, renaming to {new_name}", gid=gid)

        log("info", "mover_start", f"Moving {top_level_name} to Drive...", gid=gid)

        try:
            shutil.move(full_source_path, dest_path)
            log("info", "mover_success", f"Successfully moved to {dest_path}", gid=gid)

            # Cleanup task from aria2
            try:
                s.aria2.removeDownloadResult(gid)
            except:
                pass

        except Exception as e:
            log("error", "mover_fail", f"Failed to move file: {str(e)}", gid=gid)

    def handle_error(self, task):
        gid = task['gid']
        msg = task.get('errorMessage', 'Unknown error')
        log("error", "download_error", f"Task failed: {msg}", gid=gid)
        try:
            s.aria2.removeDownloadResult(gid)
        except:
            pass

# Start the background thread
mover_thread = BackgroundMover()
mover_thread.start()

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
    
    # BACKEND QUEUE ENFORCEMENT: Only allow one active download
    try:
        active = s.aria2.tellActive(["gid", "status"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])

        if len(active) > 0 or len(waiting) > 0:
            log("warning", "add_magnet", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
            return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
    except Exception as e:
         log("error", "add_magnet", f"Aria2 connection failed: {str(e)}")
         return jsonify({"error": "Backend not connected to Aria2"}), 500
    
    try:
        # Note: DOWNLOAD_DIR is set in aria2c startup args, but addUri inherits it.
        # We don't need to specify dir here unless we want to override.
        gid = s.aria2.addUri([magnet_link])
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
        try:
            active = s.aria2.tellActive(["gid", "status"])
            waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])

            if len(active) > 0 or len(waiting) > 0:
                log("warning", "add_torrent_file", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
                return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
        except:
             return jsonify({"error": "Backend not connected to Aria2"}), 500

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        log("info", "add_torrent_file", f"Received torrent file ({len(raw_bytes)} bytes), adding to aria2...")
        gid = s.aria2.addTorrent(binary_torrent)
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
        # We don't query stopped here because the background thread cleans them up quickly
        # But we can query it just in case
        stopped = s.aria2.tellStopped(0, 100, basic_keys)
        
        # Track GID transitions for debugging
        all_tasks = active + waiting + stopped
        all_gids = [t['gid'] for t in all_tasks]
        
        if all_gids:
            # log("info", "status_poll", f"Tracking {len(all_gids)} tasks", extra={"gids": all_gids})
            pass
        
        return jsonify({
            "active": active,
            "waiting": waiting,
            "stopped": stopped
        })
    except Exception as e:
        # Don't spam logs on every status poll failure (which happens if aria2 is down)
        # log("error", "get_status", f"Failed: {str(e)}")
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
        # Check Final Dir usage
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

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal Server Error", "details": str(error)}), 500

if __name__ == "__main__":
    log("info", "startup", "CloudLeecher Backend starting...")
    
    # Clean up any existing stalled tasks on startup
    # log("info", "startup", "Cleaning up stalled tasks from previous session...")
    
    app.run(port=5000)
