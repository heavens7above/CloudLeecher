# Quick Start Guide

Get CloudLeecher up and running in less than 5 minutes!

## What You'll Need

- 🔐 A Google account (for Google Colab and Drive)
- 🌐 A modern web browser (Chrome, Firefox, Safari, or Edge)
- 🔑 An ngrok account and auth token ([Get free token](https://dashboard.ngrok.com/signup))

---

## Step 1: Get Your Ngrok Auth Token

1. Sign up for a free ngrok account at [ngrok.com](https://dashboard.ngrok.com/signup)
2. Navigate to [Your Authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Copy your auth token (looks like: `2abc123def456_ghi789JKL012mno345PqR`)

---

## Step 2: Open the Colab Notebook

1. Open the CloudLeecher Colab notebook: [**Open Notebook**](https://colab.research.google.com/drive/1j-L-CXE-ObYWZ-_qGv0uNlpRsS3HPQSE?usp=sharing)
2. Click **"Copy to Drive"** to save a copy to your Google Drive
3. You're now working with your own copy!

---

## Step 3: Add Your Ngrok Token to Colab Secrets

1. In the Colab notebook, click the **🔑 Secrets** icon in the left sidebar
2. Click **"+ Add new secret"**
3. Enter:
   - **Name**: `NGROK-AUTHTOKEN`
   - **Value**: Your ngrok auth token from Step 1
4. Toggle **"Notebook access"** to ON
5. Click **Save**

---

## Step 4: Run the Notebook Cells

Run each cell in order by clicking the ▶️ play button on the left of each cell:

### Cell 1: Mount Google Drive
- Authorizes access to your Google Drive
- Creates download directory at `/content/drive/MyDrive/TorrentDownloads`
- Click **"Connect to Google Drive"** and sign in when prompted

### Cell 2: Install Dependencies
- Installs aria2, flask, and pyngrok
- Takes about 30 seconds
- No user interaction needed

### Cell 3: Start Aria2 Service
- Launches the download engine in the background
- No user interaction needed

### Cell 4: Create Backend API
- Generates the Flask server code
- No user interaction needed

### Cell 5: Launch Public Server
- Starts the Flask backend
- Opens ngrok tunnel
- **Copy the PUBLIC URL** that appears (looks like: `https://unique-name.ngrok-free.dev`)

**Example Output:**
```
============================================================
🔗 PUBLIC URL: https://vitalistically-falsifiable-donnette.ngrok-free.dev
============================================================

✅ CloudLeecher Backend is Online!
🌍 Frontend App: https://cloudleecher.web.app
📋 Copy the URL above (PUBLIC URL) and paste it into the CloudLeecher Frontend app.
```

> [!IMPORTANT]
> **Keep this cell running!** Don't stop it or your backend will disconnect.

---

## Step 5: Connect the Frontend

1. Open the CloudLeecher web app: [**cloudleecher.web.app**](https://cloudleecher.web.app/)
2. Click the **⚙️ Settings** icon in the top-right corner
3. Paste your PUBLIC URL from Step 4
4. Click **"Connect"**
5. You should see a ✅ **"Connected"** status

---

## Step 6: Start Downloading!

### Using a Magnet Link:
1. Find a torrent magnet link (starts with `magnet:?xt=urn:btih:`)
2. Paste it into the input field
3. Click **"Start Download"**

### Using a .torrent File:
1. Click **"Browse"** to select a .torrent file
2. The file will upload automatically
3. Download starts immediately

---

## What Happens Next?

1. **Backend**: Aria2 downloads the torrent using Google's fast network
2. **Storage**: Files are saved to your Google Drive at `/MyDrive/TorrentDownloads/`
3. **Frontend**: Shows real-time progress with speed, ETA, and file info
4. **Completion**: Files appear in your Google Drive for permanent storage

---

## Viewing Your Downloads

**In Google Drive:**
1. Open [Google Drive](https://drive.google.com)
2. Navigate to **My Drive → TorrentDownloads**
3. Find your completed downloads

**In Colab:**
1. Click the **📁 Files** icon in the left sidebar
2. Navigate to `drive/MyDrive/TorrentDownloads`

---

## Common First-Time Issues

### ❌ "Backend Check Failed"

**Problem**: Frontend can't connect to backend

**Solutions**:
- Verify Cell 5 is still running (has a spinning indicator)
- Check that you copied the FULL ngrok URL (including `https://`)
- Make sure your ngrok auth token is correct in Colab Secrets
- Try refreshing the Colab page and re-running Cell 5

### ❌ "Another download is already in progress"

**Problem**: Queue limit enforced

**Solution**:
- CloudLeecher only allows 1 download at a time to preserve Colab resources
- Wait for the current download to complete
- Or remove the current download using the ❌ button

### ❌ Colab session disconnected

**Problem**: Colab timed out due to inactivity

**Solution**:
- Colab free tier disconnects after ~60 minutes of inactivity
- Re-run Cell 5 to get a NEW ngrok URL
- Update the URL in the frontend settings

### ❌ ngrok error "ERR_NGROK_108"

**Problem**: Auth token not configured correctly

**Solution**:
- Double-check the secret name is exactly `NGROK-AUTHTOKEN` (case-sensitive)
- Ensure "Notebook access" is toggled ON
- Verify your auth token is valid at [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)

---

## Tips for Success

### 💡 Keep Colab Active
- Colab free tier disconnects after inactivity
- Keep the tab open or use [Colab Alive](https://chrome.google.com/webstore/detail/colab-alive/eookkckfbbgnhdgcbfbicoahejkdoele) extension

### 💡 Monitor Your Drive Space
- Free Google Drive has 15 GB limit
- Check storage before large downloads
- Delete old downloads to free space

### 💡 Choose Healthy Torrents
- More seeders = faster downloads
- Dead torrents may stall or fail
- Use reputable torrent sites

### 💡 Download One at a Time
- Better performance with focused resources
- Prevents Colab memory issues
- Faster completion times

---

## Next Steps

- 📖 Read the [Architecture Overview](./ARCHITECTURE.md) to understand how it works
- 🔧 Check out [Troubleshooting](./TROUBLESHOOTING.md) for more solutions
- 💻 Learn about [Development Setup](./DEVELOPMENT.md) to customize CloudLeecher
- 🤝 See [Contributing](./CONTRIBUTING.md) to help improve the project

---

## Need Help?

- 🐛 [Report an Issue](https://github.com/heavens7above/CloudLeecher/issues)
- 💬 [Ask a Question](https://github.com/heavens7above/CloudLeecher/discussions)
- 📧 Check the [FAQ](./FAQ.md)

---

**Happy Leeching! 🌩️**
