# Frequently Asked Questions

Common questions and answers about CloudLeecher.

## General Questions

### What is CloudLeecher?

CloudLeecher is a free, open-source cloud-based torrent downloader that uses Google Colab's infrastructure to download torrents directly to your Google Drive. It consists of a React frontend hosted on Firebase and a Python/Flask backend running on Google Colab.

### Is CloudLeecher really free?

Yes! CloudLeecher is completely free and open-source. It uses:
- Google Colab (free tier)
- Google Drive (free 15GB)
- Firebase Hosting (free tier)
- ngrok (free tier)

### Is CloudLeecher legal?

CloudLeecher itself is a legal tool. However, downloading copyrighted content without permission is illegal in most countries. Only use CloudLeecher for:
- Public domain content
- Creative Commons licensed files
- Content you have permission to download
- Legal torrents (Linux ISOs, open-source software, etc.)

---

## Usage Questions

### How do I get started?

See our [Quick Start Guide](./QUICK_START.md) for step-by-step instructions. In summary:
1. Get ngrok auth token
2. Open Colab notebook
3. Add auth token to Colab Secrets
4. Run all cells
5. Copy ngrok URL to frontend

### Can I download multiple torrents at once?

No. CloudLeecher enforces a single download at a time to:
- Conserve Colab's limited resources
- Prevent memory/bandwidth exhaustion
- Ensure better performance per download
- Reduce risk of session termination

### How long can downloads run?

Google Colab free tier sessions:
- Last ~12 hours maximum
- Disconnect after ~60 minutes of inactivity
- May disconnect earlier during peak usage

For long downloads (>8 hours), consider:
- Colab Pro ($10/month) for longer sessions
- Breaking into smaller parts
- Using during off-peak hours

### Where are my files saved?

Files are saved to your Google Drive at:
```
My Drive/TorrentDownloads/
```

You can access them:
- In Google Drive web interface
- In Colab Files sidebar
- Via Google Drive desktop app

### Can I download to a different location?

Yes, edit the `DOWNLOAD_DIR` in:
1. Colab Cell 1: Change the mount path
2. Colab Cell 4: Update `DOWNLOAD_DIR` in app.py

Example:
```python
DOWNLOAD_DIR = "/content/drive/MyDrive/MyCustomFolder"
```

---

## Technical Questions

### Why does the GID change during download?

Aria2 sometimes spawns new tasks during the download process:
1. **Metadata GID**: Initial task to download .torrent metadata
2. **Download GID**: Actual file download task

The backend tracks these transitions via `followedBy` and `following` fields. The frontend automatically updates to the new GID.

### What is ngrok and why is it needed?

ngrok creates a secure tunnel from the internet to your Colab backend. It's needed because:
- Colab doesn't provide public IPs
- Frontend needs to communicate with backend
- ngrok provides an HTTPS endpoint

### Can I use a custom domain instead of ngrok?

Not easily with the free setup. Advanced users could:
- Use ngrok paid tier (custom domains)
- Set up Cloudflare tunnels
- Use other tunneling services

This requires modifying the backend code.

### What happens if Colab disconnects?

1. Backend becomes inaccessible
2. Downloads pause/stop
3. Frontend shows "Backend Check Failed"

**Recovery:**
- Reconnect Colab runtime
- Re-run all cells (get new ngrok URL)
- Update URL in frontend
- Re-add downloads (files partially downloaded remain in Drive)

### Can I use Colab Pro?

Yes! Colab Pro offers:
- Longer session durations
- Better GPU/CPU resources
- Priority access
- Background execution

CloudLeecher works identically on Colab Pro.

---

## Troubleshooting Questions

### Why can't the frontend connect to backend?

Common causes:
1. **Cell 5 not running**: Check for spinning indicator
2. **Wrong URL**: Ensure you copied full ngrok URL
3. **ngrok expired**: Restart Cell 5 for new URL
4. **Auth token issue**: Verify Colab Secret setup

See [Troubleshooting Guide](./TROUBLESHOOTING.md) for detailed solutions.

### Why is my download stuck at 0%?

Possible reasons:
1. **Dead torrent**: No seeders available
2. **Metadata download**: Wait 30-60 seconds
3. **GID transition**: Check backend logs
4. **Aria2 issue**: Restart Aria2 (Cell 3)

### Why do I see "[Lost]" status?

This indicates a GID mismatch between frontend and backend. Usually caused by:
- Frontend tracking old metadata GID
- Backend switched to new download GID

**Solution:**
- Check backend logs for transitions
- Remove [Lost] task from frontend
- Check Google Drive (files may be there!)

### Out of disk space error?

Google Drive free tier has 15GB total. To fix:
1. Check Drive storage: https://drive.google.com/settings/storage
2. Delete old downloads
3. Empty Drive trash
4. Remove large Gmail attachments
5. Consider Google One upgrade

---

## Performance Questions

### Why are downloads slow?

Factors affecting speed:
1. **Torrent health**: Few seeders = slow speed
2. **Colab network**: Variable speeds, especially during peak hours
3. **Peer location**: Geographic distance to seeders
4. **Free tier limits**: Colab may throttle during peak usage

**Tips for faster downloads:**
- Choose torrents with 50+ seeders
- Download during off-peak hours (late night/early morning)
- Use well-established torrent sources

### What's the maximum download speed?

Theoretical maximum: 100+ Mbps (Google's bandwidth)
Real-world: Usually 10-50 Mbps depending on torrent health

### Can I increase the speed?

Aria2 is already configured for maximum speed:
- 16 connections per server
- 16-way file splitting
- No bandwidth limits

The main bottleneck is usually torrent health and Colab network conditions.

---

## Security & Privacy Questions

### Is my data private?

**Backend (Colab):**
- Each session is isolated
- No data persists after session ends
- Only you can access your Colab instance

**Frontend:**
- No user accounts
- No data uploaded to CloudLeecher servers
- All data stays in your Google Drive

**Communication:**
- HTTPS via ngrok
- Direct browser-to-Colab connection
- No intermediate servers

### Can others access my downloads?

Only if you share:
- Your ngrok URL (anyone with URL can control your backend)
- Your Google Drive (standard Drive sharing permissions)

**Best practices:**
- Never share ngrok URL
- Each session gets new URL (not predictable)
- Set proper Drive permissions

### What data is collected?

**CloudLeecher collects:**
- Nothing! No analytics, no tracking, no user data

**Third parties may collect:**
- Google Colab: Usage metrics per their policy
- ngrok: Connection logs per their policy
- Firebase: Basic hosting analytics (anonymized)

---

## Deployment Questions

### Can I self-host the frontend?

Yes! The frontend is a static site. Host anywhere:
```bash
cd frontend
npm run build
# Upload dist/ folder to any static host
```

Options:
- GitHub Pages
- Netlify
- Vercel
- Your own server

### Can I run the backend outside Colab?

Yes, but you lose the main benefits (free cloud resources, Google Drive integration). You'd need:
- A server/VPS
- aria2 installed
- Python environment
- Public IP or tunneling solution

### Can I make CloudLeecher private?

Current version has no authentication. To add:
1. Add authentication to backend (JWT, API keys, etc.)
2. Add login to frontend
3. Implement user sessions

This requires significant code changes.

---

## Feature Questions

### Will CloudLeecher support multi-user?

Possibly in the future. Challenges:
- Colab sessions are single-user
- Would need separate backend deployment
- Authentication system required

### Will there be a mobile app?

Currently no mobile app, but the web interface is mobile-responsive. A native app would require:
- Dedicated backend (not Colab)
- Mobile app development
- Ongoing maintenance

### Can CloudLeecher download from direct links (HTTP/FTP)?

Aria2 supports this! To add:
1. Add new endpoint in backend
2. Call `aria2.addUri([url])` for direct links
3. Update frontend UI

This is a potential future feature.

### Can I schedule downloads?

Not currently. This would require:
- Task scheduling system
- Persistent database
- Always-on backend

For now, add downloads manually when ready.

---

## Comparison Questions

### CloudLeecher vs seedr/zbigz?

| Feature | CloudLeecher | Paid Services |
|---------|--------------|---------------|
| Cost | Free | $5-15/month |
| Speed | Variable | Usually faster |
| Storage | Your Google Drive | Their servers |
| Privacy | Full control | Third-party storage |
| Session time | Colab limits | Unlimited |
| Setup | Manual | Ready to use |

### CloudLeecher vs local torrenting?

| Factor | CloudLeecher | Local |
|--------|--------------|-------|
| Hardware wear | None | High |
| Power usage | None | Continuous |
| Bandwidth | Cloud's | Your ISP's |
| IP exposure | Cloud's IP | Your IP |
| Speed | Variable | Depends on ISP |
| Setup | More complex | Simpler |

---

## Contribution Questions

### How can I contribute?

See [Contributing Guide](./CONTRIBUTING.md) for:
- Reporting bugs
- Suggesting features
- Improving docs
- Submitting code

### I found a bug, what should I do?

1. Check [existing issues](https://github.com/heavens7above/CloudLeecher/issues)
2. If new, create an issue with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Screenshots/logs
   - Environment details

### I have a feature idea

Great! Open a [feature request](https://github.com/heavens7above/CloudLeecher/issues/new):
- Explain the use case
- Describe proposed solution
- Mention alternatives considered

---

## Still Have Questions?

- **Documentation**: Check other docs in `/docs`
- **GitHub Issues**: [Search existing issues](https://github.com/heavens7above/CloudLeecher/issues)
- **Discussions**: [Ask the community](https://github.com/heavens7above/CloudLeecher/discussions)
- **Quick Start**: [Getting Started Guide](./QUICK_START.md)
- **Troubleshooting**: [Common Problems](./TROUBLESHOOTING.md)
