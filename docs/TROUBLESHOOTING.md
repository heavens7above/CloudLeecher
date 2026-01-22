# Troubleshooting Guide

Common issues and their solutions for CloudLeecher.

## Table of Contents

- [Backend Connection Issues](#backend-connection-issues)
- [Download Problems](#download-problems)
- [Google Drive Issues](#google-drive-issues)
- [Colab Session Issues](#colab-session-issues)
- [Frontend Issues](#frontend-issues)
- [Performance Issues](#performance-issues)

---

## Backend Connection Issues

### ❌ "Backend Check Failed" in Frontend

**Symptoms:**
- Orange warning banner in frontend
- Cannot add downloads
- Status not updating

**Possible Causes & Solutions:**

#### 1. Backend Not Running
**Check**: Is Cell 5 in Colab still running?
- Look for spinning indicator on Cell 5
- Check for any error messages in Colab output

**Solution**: Re-run Cell 5 to restart backend

#### 2. Wrong ngrok URL
**Check**: Did you copy the full URL correctly?
- URL should start with `https://`
- URL should end with `.ngrok-free.dev` or `.ngrok.io`
- No trailing slashes

**Solution**: Copy the URL again from Colab Cell 5 output

#### 3. ngrok Tunnel Expired
**Check**: How long has the session been running?
- Free ngrok tunnels can expire after 2 hours

**Solution**:
```
1. Stop Cell 5 (click stop button)
2. Re-run Cell 5
3. Copy the NEW ngrok URL
4. Update URL in frontend settings
```

#### 4. CORS Issues
**Check**: Browser console for CORS errors
- Open DevTools (F12)
- Look in Console tab

**Solution**: Ensure backend has `flask-cors` installed (Cell 2)

---

### ❌ ngrok Error "ERR_NGROK_108"

**Symptoms:**
- Cell 5 fails with ngrok authentication error

**Solution:**
```
1. Go to Colab sidebar → 🔑 Secrets
2. Verify secret name is EXACTLY: NGROK-AUTHTOKEN
3. Ensure "Notebook access" is ON
4. Get new auth token from https://dashboard.ngrok.com/get-started/your-authtoken
5. Update secret value
6. Re-run Cell 5
```

---

### ❌ "Failed to connect to backend" in Logs

**Symptoms:**
- Frontend shows connection errors in backend logs panel

**Diagnostic Steps:**
```
1. Test backend directly in browser:
   - Visit: https://your-ngrok-url.ngrok-free.dev/health
   - Should return: {"status": "ok", "service": "CloudLeecher-Backend"}

2. If 502 Bad Gateway:
   - Backend (Flask) is not running
   - Re-run Cell 5

3. If timeout:
   - Network issue or ngrok tunnel down
   - Re-run Cell 5 for new tunnel
```

---

## Download Problems

### ❌ Download Stuck at "Downloading Metadata"

**Symptoms:**
- Status shows "active" but no progress
- 0% completion for extended time

**Possible Causes:**

#### 1. Dead Torrent
**Check**: Does the torrent have seeders?

**Solution**:
- Use torrents with healthy peer counts
- Try a different torrent source
- Remove stalled download and try another

#### 2. GID Transition
**Check**: Backend logs for GID changes

**Solution**:
- Wait 30-60 seconds for metadata download
- Check backend logs panel for "gid_transition" messages
- Frontend should auto-update to new GID

#### 3. Aria2 Connection Lost
**Check**: Backend logs for aria2 errors

**Solution**:
```
1. In Colab, run Cell 3 again to restart Aria2
2. Then run Cell 5 again to restart backend
3. Add download again
```

---

### ❌ "Another download is already in progress"

**Symptoms:**
- Cannot add new download
- Error message when trying to add magnet/file

**Reason:**
- Backend enforces 1 active download at a time
- Prevents Colab resource exhaustion

**Solution:**
```
Option 1: Wait for current download to complete

Option 2: Remove current download
  1. Click ❌ button on active task
  2. Try adding new download

Option 3: Force cleanup (nuclear option)
  1. Open browser DevTools console
  2. Run: fetch('YOUR_NGROK_URL/api/cleanup', {method: 'POST'})
  3. Reload frontend
```

---

### ❌ Download Shows "[Lost]" Status

**Symptoms:**
- Task shows "[Lost]" in frontend
- Backend logs show download completing successfully

**Cause:**
- GID mismatch between frontend and backend
- Frontend tracking old GID, backend using new GID

**Solution:**
```
1. Check backend logs for gid_transition messages
2. Remove the [Lost] task from frontend (click ❌)
3. Check Google Drive - files may actually be there!
4. If issue persists:
   - Clear browser localStorage
   - Refresh page
   - Reconnect to backend
```

---

### ❌ Download Fails with Error

**Symptoms:**
- Status changes to "error"
- Error message displayed

**Common Error Codes:**

| Error Code | Meaning | Solution |
|------------|---------|----------|
| 3 | File I/O error | Check Drive space |
| 7 | Invalid metadata | Re-add torrent |
| 9 | Not enough disk space | Free up Drive storage |
| 24 | Connection timeout | Try again, check torrent health |

**General Solution:**
```
1. Note the error message
2. Remove the failed task
3. Check Google Drive space
4. Try adding a different torrent to test
5. If persistent, restart backend (Cell 5)
```

---

## Google Drive Issues

### ❌ "Not enough disk space" Error

**Symptoms:**
- Downloads fail with error code 9
- Cannot start new downloads

**Solution:**
```
1. Check Drive storage:
   - Visit https://drive.google.com/settings/storage

2. Free up space:
   - Delete old downloads from /TorrentDownloads/
   - Empty Google Drive trash
   - Remove large Gmail attachments

3. Verify available space before downloading:
   - Frontend shows Drive space if backend connected
```

---

### ❌ Cannot Find Downloaded Files

**Symptoms:**
- Download shows complete but files not visible

**Check Locations:**
```
1. In Google Drive web:
   - Navigate to My Drive → TorrentDownloads

2. In Colab Files sidebar:
   - drive/MyDrive/TorrentDownloads

3. If not there:
   - Check backend logs for actual save location
   - Files may be in /content/drive/MyDrive/TorrentDownloads
```

**Solution:**
- If files missing after successful download, check Colab Cell 1 mount status
- Re-mount Drive if needed
- Check if Drive quota exceeded

---

### ❌ "Drive already mounted" Warning

**Symptoms:**
- Cell 1 shows warning when re-run

**Is This a Problem?**
- No! This is normal
- Drive is already connected
- Continue to next cells

---

## Colab Session Issues

### ❌ "Runtime Disconnected"

**Symptoms:**
- Colab shows "Cannot connect to runtime"
- Backend becomes unreachable

**Causes:**
- Inactivity timeout (~60 minutes free tier)
- Runtime crashed
- Long-running downloads outlasted session

**Solution:**
```
1. Click "Reconnect" in Colab
2. Re-run ALL cells (1 through 5)
3. Get NEW ngrok URL from Cell 5
4. Update URL in frontend
5. Add downloads again
```

**Prevention:**
- Keep Colab tab active
- Occasionally interact with Colab
- Use browser extensions like "Colab Alive"

---

### ❌ "Resource Exhausted" Error

**Symptoms:**
- Colab crashes during download
- Out of memory errors

**Cause:**
- Multiple simultaneous downloads (if modified)
- Very large torrents

**Solution:**
```
1. Stick to ONE download at a time
2. For large files (>5GB), monitor memory in Colab:
   - Runtime → Manage Sessions
3. If crashes persist, use GPU runtime:
   - Runtime → Change runtime type → GPU
```

---

## Frontend Issues

### ❌ Tasks Not Updating

**Symptoms:**
- Progress bars frozen
- Speed showing 0 MB/s but download active

**Solution:**
```
1. Check browser console for errors (F12)
2. Verify backend connection (green status indicator)
3. Hard refresh: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
4. Clear browser cache and reload
```

---

### ❌ Cannot Upload .torrent File

**Symptoms:**
- File upload does nothing
- No error message

**Solution:**
```
1. Check file size (should be < 1MB for .torrent files)
2. Verify file extension is .torrent
3. Try magnet link instead
4. Check browser console for JavaScript errors
```

---

### ❌ Layout Issues on Mobile

**Symptoms:**
- Elements overlapping
- Text cut off
- Buttons not clickable

**Solution:**
```
1. Refresh page
2. Try landscape orientation
3. Update to latest Chrome/Safari
4. Clear browser cache
```

---

## Performance Issues

### ❌ Slow Download Speeds

**Symptoms:**
- Speed stuck at KB/s instead of MB/s
- Downloads taking much longer than expected

**Possible Causes:**

#### 1. Poor Torrent Health
**Check**: Number of seeders
- Look at seeder count in task details
- 0-5 seeders = slow
- 10+ seeders = good
- 50+ seeders = excellent

**Solution**: Choose torrents with more seeders

#### 2. Aria2 Configuration
**Check**: Current config is optimized

**Solution**: Aria2 is pre-configured for max speed:
- 16 connections per server
- 16 split chunks
- No bandwidth limits

#### 3. Colab Network Limits
**Reality Check**:
- Free tier has variable speeds
- Peak times may be slower
- No control over Google's network

**Solution**: Be patient, try different times of day

---

### ❌ High CPU/Memory in Colab

**Symptoms:**
- Colab shows high resource usage
- Risk of disconnection

**Solution:**
```
1. Stick to ONE download at a time
2. Avoid adding multiple waiting tasks
3. Remove completed downloads promptly
4. Use cleanup endpoint to clear all tasks
```

---

## Debug Mode

### Enable Detailed Logging

**In Backend (Colab):**
Already enabled! Check Cell 5 output for logs.

**In Frontend (Browser):**
```javascript
// Open browser console (F12)
localStorage.setItem('debug', 'true');
// Reload page
// All API calls will be logged
```

**View Backend Logs in Frontend:**
- Scroll to bottom of page
- "Backend Logs" section shows recent operations

---

## Getting Help

If none of these solutions work:

1. **Collect Information:**
   ```
   - What were you trying to do?
   - What error message did you see?
   - Browser console errors (F12 → Console)
   - Backend logs from Colab or frontend panel
   ```

2. **Check Existing Issues:**
   - [GitHub Issues](https://github.com/heavens7above/CloudLeecher/issues)

3. **Create New Issue:**
   - Include all info from step 1
   - Describe steps to reproduce
   - Mention your setup (browser, Colab tier, etc.)

4. **Ask Community:**
   - [GitHub Discussions](https://github.com/heavens7above/CloudLeecher/discussions)

---

## Quick Diagnostic Checklist

Use this checklist to diagnose most issues:

- [ ] Colab Cell 5 is running (spinning indicator)
- [ ] ngrok URL is up to date in frontend
- [ ] Backend health check returns OK: `https://YOUR-URL/health`
- [ ] Google Drive has free space
- [ ] Only 1 download active at a time
- [ ] Browser console shows no errors
- [ ] Backend logs panel shows recent activity
- [ ] Torrent has seeders (for new downloads)
- [ ] .torrent file is valid (if using file upload)

If all checkmarks pass and still having issues, see "Getting Help" above.
