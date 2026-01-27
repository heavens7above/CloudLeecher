# Production Readiness Audit & Fixes

## 1. Backend ↔ Frontend Communication

**Issue**: The communication was insecure and prone to "ghost" tasks due to efficient polling but lack of strict state synchronization. The backend did not enforce authentication.

**Fixes Applied**:
*   **Security**: Implemented `x-api-key` authentication. The backend now checks for `CLOUDLEECHER_API_KEY` environment variable or generates a secure random key on startup.
*   **Frontend**: Updated `api.js` to send the `x-api-key` header.
*   **State**: Frontend `AppContext` now manages the API Key and persists it.

**Recommendation**: Ensure the user copies the API Key from the Colab output logs to the Frontend settings.

## 2. Torrent → Google Drive Download Failure

**Issue**: Downloading directly to Google Drive (`/content/drive/MyDrive/...`) causes I/O errors and timeouts because FUSE filesystems handle random-access writes (typical of BitTorrent) poorly.

**Fixes Applied**:
*   **Staging**: Changed `DOWNLOAD_DIR` to a local temporary directory (`/content/temp_downloads`).
*   **File Mover**: Implemented a `BackgroundMonitor` thread in `app.py` that watches for completed tasks.
*   **Atomic Move**: Once a download is complete, the monitor moves the file/folder to Google Drive (`/content/drive/MyDrive/TorrentDownloads`).
*   **Cleanup**: After moving, the task is removed from `aria2` to prevent re-downloading, and the backend maintains a `history_log` so the frontend still displays it as "Completed".

## 3. Production Readiness Audit

### Architecture
*   **Statefulness**: The backend relies on in-memory state (`logs`, `history_log`) and `aria2` process state. In a Colab environment, this is acceptable as sessions are ephemeral.
*   **Concurrency**: Enabled `threaded=True` in `app.run()`. For higher load, a WSGI server like `gunicorn` is recommended, but `flask` dev server is often sufficient for single-user Colab instances.

### Reliability
*   **File Collisions**: The file mover now appends a timestamp (`_YYYYMMDD_HHMMSS`) if a file with the same name exists in the destination.
*   **Stalled Tasks**: The backend includes `purge_stalled_downloads` on startup to clean up debris from previous runs.

### Observability
*   **Logging**: Logs are written to `/content/backend_logs.json` and printed to console. The frontend has a log viewer.
*   **Status**: The `/api/status` endpoint now merges active aria2 tasks with the internal "moved to drive" history, providing a unified view.

### Security
*   **Secrets**: API Key is now required.
*   **Exposure**: `ngrok` exposes the local port. The API Key prevents unauthorized access via the public URL.

## Minimum Changes Required Checklist
- [x] Set `CLOUDLEECHER_API_KEY` in environment or use generated key.
- [x] Update Frontend `api.js` to send key.
- [x] Update Backend `app.py` to check key.
- [x] Switch `DOWNLOAD_DIR` to local temp.
- [x] Implement background file mover.
