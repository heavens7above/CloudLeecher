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
import string
from datetime import datetime
from collections import deque

app = Flask(__name__)
CORS(app)

# Configuration
# Use a temp directory for initial download to avoid Drive FUSE issues
TEMP_DOWNLOAD_DIR = "/content/temp_downloads"
DOWNLOAD_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
LOG_FILE = "/content/backend_logs.json"

# Ensure directories exist
os.makedirs(TEMP_DOWNLOAD_DIR, exist_ok=True)
# DOWNLOAD_DIR creation is handled in the notebook usually, but good to be safe
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# API Key Configuration
# Get from environment or generate a random one
API_KEY = os.environ.get("CLOUDLEECHER_API_KEY")
if not API_KEY:
    chars = string.ascii_letters + string.digits
    API_KEY = ''.join(secrets.choice(chars) for _ in range(32))
    print(f"\n{'='*60}")
    print(f"🔑 API KEY GENERATED: {API_KEY}")
    print(f"⚠️  Copy this key to the CloudLeecher Frontend Settings!")
    print(f"{'='*60}\n")
else:
    print(f"🔑 Using API Key from Environment")

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
def require_api_key():
    # Allow health check and CORS options without key
    if request.method == 'OPTIONS' or request.path == '/health':
        return

    key = request.headers.get('x-api-key')
    if not key or key != API_KEY:
        log("warning", "auth", f"Unauthorized access attempt from {request.remote_addr}")
        return jsonify({"error": "Unauthorized: Invalid or missing API Key"}), 401

# --- Background Worker: Move Completed Files to Drive ---
class DriveMoverThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.processed_gids = set()

    def run(self):
        log("info", "mover_thread", "Drive Mover Service Started")
        while self.running:
            try:
                # Poll stopped/completed tasks
                # we look at tellStopped to find completed tasks
                stopped = s.aria2.tellStopped(0, 100, ["gid", "status", "files", "dir"])

                for task in stopped:
                    gid = task['gid']
                    status = task['status']

                    if status == 'complete' and gid not in self.processed_gids:
                        self.process_completed_task(task)
                        self.processed_gids.add(gid)

            except Exception as e:
                # Don't spam logs if aria2 is down/restarting
                if "Connection refused" not in str(e):
                    log("error", "mover_thread", f"Error in loop: {e}")

            time.sleep(5) # Check every 5 seconds

    def process_completed_task(self, task):
        gid = task['gid']
        try:
            files = task['files']
            if not files:
                return

            # Determine the root path of the download
            # Aria2 returns file paths. We need to find the common root directory or file.
            # If it's a single file torrent, path is directly the file.
            # If multi-file, they are in a subdirectory usually.

            source_path = files[0]['path']

            # Check if source is in TEMP directory
            if TEMP_DOWNLOAD_DIR not in source_path:
                # Already in drive or elsewhere, skip
                return

            # Logic to find what exactly to move.
            # If it's a multi-file torrent, aria2 creates a directory.
            # We want to move that directory.
            # If it's a single file, we move the file.

            # We can use the 'dir' property from task if available, but it points to base dir.
            # Let's inspect the relative path.
            # If the file path is "{TEMP}/{Name}/{File}", we move "{TEMP}/{Name}".
            # If file path is "{TEMP}/{File}", we move "{TEMP}/{File}".

            # Simplification: The file structure in TEMP mirrors what we want in DRIVE.
            # However, aria2 structure can be complex.
            # Strategy: Move the specific file(s) or the top-level folder created.

            # Better approach:
            # 1. Get the relative path of the first file relative to TEMP_DOWNLOAD_DIR
            rel_path = os.path.relpath(source_path, TEMP_DOWNLOAD_DIR)

            # Get the top-level component
            top_level = rel_path.split(os.sep)[0]

            full_source_path = os.path.join(TEMP_DOWNLOAD_DIR, top_level)
            dest_path = os.path.join(DOWNLOAD_DIR, top_level)

            log("info", "mover", f"Moving '{top_level}' to Drive...", gid=gid)

            # Handle collision
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(top_level)
                counter = 1
                while os.path.exists(dest_path):
                    new_name = f"{base}_{counter}{ext}"
                    dest_path = os.path.join(DOWNLOAD_DIR, new_name)
                    counter += 1
                log("warning", "mover", f"Destination exists. Renaming to {os.path.basename(dest_path)}", gid=gid)

            # Move
            shutil.move(full_source_path, dest_path)
            log("info", "mover", f"Successfully moved to: {dest_path}", gid=gid)

            # We do NOT remove the download result from aria2 here,
            # so the frontend still sees it as "complete".
            # The frontend shows the file path, which will still point to the old location
            # in aria2's memory, but that's just a string.
            # We could verify file existence in frontend, but for now this is fine.

        except Exception as e:
            log("error", "mover", f"Failed to move file: {e}", gid=gid)

# Start background thread
mover_thread = DriveMoverThread()
mover_thread.start()


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
    active = s.aria2.tellActive(["gid", "status"])
    waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
    
    if len(active) > 0 or len(waiting) > 0:
        log("warning", "add_magnet", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
        return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429
    
    try:
        # Enforce download to TEMP directory
        options = {"dir": TEMP_DOWNLOAD_DIR}
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

        # BACKEND QUEUE ENFORCEMENT
        active = s.aria2.tellActive(["gid", "status"])
        waiting = s.aria2.tellWaiting(0, 100, ["gid", "status"])
        
        if len(active) > 0 or len(waiting) > 0:
            log("warning", "add_torrent_file", f"Rejected: {len(active)} active, {len(waiting)} waiting tasks already exist")
            return jsonify({"error": "Another download is already in progress. Please wait for it to complete."}), 429

        raw_bytes = base64.b64decode(b64_content)
        binary_torrent = xmlrpc.client.Binary(raw_bytes)
        
        log("info", "add_torrent_file", f"Received torrent file ({len(raw_bytes)} bytes), adding to aria2...")

        # Enforce download to TEMP directory
        options = {"dir": TEMP_DOWNLOAD_DIR}
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
                    log("info", "gid_transition", f"Task spawned follow-up", 
                        gid=task['gid'], 
                        extra={"followedBy": task['followedBy']})
            
            if task.get('following'):
                # This task is following another
                log("info", "gid_transition", f"Task is following {task['following']}", 
                    gid=task['gid'])
        
        if all_gids:
            log_msg = f"Currently tracking {len(all_gids)} tasks"
            if gid_transitions:
                log_msg += f" | Transitions: {', '.join(gid_transitions)}"
            # Reduce log spam
            # log("info", "status_poll", log_msg, extra={"gids": all_gids})
        
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
        total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
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
            # Remove completed or errored tasks
            if task['status'] in ['error', 'removed']: # Removed 'complete' to give mover thread time to see it
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
    
    # Clean up any existing stalled tasks on startup
    log("info", "startup", "Cleaning up stalled tasks from previous session...")
    purge_stalled_downloads()
    
    app.run(port=5000)
