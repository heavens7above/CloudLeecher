# Deployment Guide

This guide covers deploying CloudLeecher's components.

## Overview

CloudLeecher has two deployment components:

1. **Frontend**: Static React app → Firebase Hosting
2. **Backend**: Google Colab notebook (user-deployed)

---

## Frontend Deployment

### Prerequisites

- Node.js 18+
- Firebase account
- Firebase CLI installed

### 1. Install Firebase CLI

```bash
npm install -g firebase-tools
```

### 2. Login to Firebase

```bash
firebase login
```

### 3. Initialize Firebase (First Time Only)

```bash
cd frontend
firebase init hosting
```

Configuration:
- **Public directory**: `dist`
- **Single-page app**: Yes
- **Automatic builds**: No (we build manually)

### 4. Build the Frontend

```bash
npm install
npm run build
```

This creates optimized production files in `frontend/dist/`

### 5. Deploy to Firebase

```bash
firebase deploy --only hosting
```

### 6. Access Deployed Site

Firebase will output your app URL:
```
✔  Deploy complete!

Project Console: https://console.firebase.google.com/project/YOUR-PROJECT/overview
Hosting URL: https://YOUR-PROJECT.web.app
```

---

## Backend Deployment (Colab)

The backend is deployed by end users, not centrally. You distribute the notebook.

### Update Colab Notebook

1. **Edit `backend/CloudLeecher.ipynb`** locally
2. **Upload to Google Colab**:
   - Go to [Google Colab](https://colab.research.google.com/)
   - File → Upload notebook
   - Select `CloudLeecher.ipynb`

3. **Get Shareable Link**:
   - Click "Share" button
   - Set to "Anyone with the link can view"
   - Copy the link

4. **Update Documentation**:
   - Update README.md with new Colab link
   - Update docs with new link

### Sync app.py and Notebook

**Critical**: Keep these in sync:
- `backend/app.py`
- Cell 4 in `backend/CloudLeecher.ipynb` (%%writefile section)

When you update one, update the other!

---

## Environment Configuration

### Frontend Environment Variables

Create `frontend/.env.production`:

```bash
# Optional: Set default API URL
VITE_API_URL=
```

For production, API URL is provided by user at runtime.

### Backend Environment (Colab)

Users configure via Colab Secrets:
- `NGROK-AUTHTOKEN`: Their ngrok auth token

No other environment variables needed.

---

## Firebase Configuration

### Firebase Hosting Configuration

File: `frontend/firebase.json`

```json
{
  "hosting": {
    "public": "dist",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

### Firebase Project Selection

File: `frontend/.firebaserc`

```json
{
  "projects": {
    "default": "your-project-id"
  }
}
```

---

## Continuous Deployment

### GitHub Actions (Optional)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Firebase

on:
  push:
    branches: [ main ]
    paths:
      - 'frontend/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          
      - name: Install dependencies
        working-directory: ./frontend
        run: npm ci
        
      - name: Build
        working-directory: ./frontend
        run: npm run build
        
      - name: Deploy to Firebase
        uses: FirebaseExtended/action-hosting-deploy@v0
        with:
          repoToken: '${{ secrets.GITHUB_TOKEN }}'
          firebaseServiceAccount: '${{ secrets.FIREBASE_SERVICE_ACCOUNT }}'
          projectId: your-project-id
          channelId: live
```

---

## Custom Domain (Optional)

### 1. Add Domain to Firebase

```bash
firebase hosting:channel:deploy production --only hosting
```

### 2. Configure DNS

Add these records to your domain DNS:

```
Type: A
Name: @
Value: 151.101.1.195

Type: A
Name: @
Value: 151.101.65.195

Type: TXT
Name: @
Value: [Firebase verification code]
```

### 3. Verify in Firebase Console

- Go to Firebase Console → Hosting
- Add custom domain
- Follow verification steps

---

## Production Checklist

### Frontend

- [ ] Build completes without errors
- [ ] All features work in production build
- [ ] API URL input validated
- [ ] Mobile responsive
- [ ] HTTPS enabled
- [ ] Error boundaries in place
- [ ] Loading states for all async operations

### Backend (Colab Notebook)

- [ ] All cells run successfully
- [ ] ngrok authentication works
- [ ] Aria2 starts correctly
- [ ] Flask app launches
- [ ] API endpoints respond
- [ ] Logging works
- [ ] Error handling in place

### Documentation

- [ ] README updated with correct links
- [ ] Colab link is shareable
- [ ] Quick Start guide accurate
- [ ] API docs match implementation
- [ ] Troubleshooting guide updated

---

## Monitoring

### Frontend Monitoring

**Firebase Console:**
- Visit: https://console.firebase.google.com/
- Check Hosting analytics
- Monitor bandwidth usage

**Browser Console:**
- Check for JavaScript errors
- Monitor API call failures

### Backend Monitoring

Users monitor their own Colab sessions:
- Colab output for backend logs
- Frontend "Backend Logs" panel
- Google Drive for completed downloads

---

## Rollback Procedures

### Frontend Rollback

```bash
# List hosting versions
firebase hosting:clone --only hosting

# Rollback to previous version
firebase hosting:clone SOURCE_SITE_ID:SOURCE_CHANNEL TARGET_SITE_ID:live
```

Or in Firebase Console:
- Hosting → Release history
- Click on previous version
- "Rollback"

### Backend Rollback

Keep previous versions of the Colab notebook:
1. Save versions in Google Drive with dates
2. If issue found, share older version
3. Update documentation links

---

## Scaling Considerations

### Current Limitations

- **Frontend**: Firebase free tier limits
  - 10 GB storage
  - 360 MB/day transfer
  - Should be sufficient for static files

- **Backend**: Not centrally hosted
  - Each user runs own Colab instance
  - No scaling needed on your end

### If Traffic Grows

Frontend options:
1. **Firebase Blaze Plan** (pay-as-you-go)
2. **CDN**: Cloudflare in front of Firebase
3. **Alternative hosting**: Vercel, Netlify

Backend remains user-deployed (no scaling needed).

---

## Security Best Practices

### Frontend

- Serve over HTTPS only (Firebase default)
- No sensitive data in frontend code
- Input validation for API URLs
- Content Security Policy headers

### Backend

Users are responsible for their Colab security:
- Keep ngrok tokens private
- Don't share ngrok URLs
- Use Colab's built-in security

### Repository

- Don't commit secrets
- Use `.gitignore` for sensitive files
- Review PRs for accidental secret inclusion

---

## Maintenance

### Regular Tasks

**Weekly:**
- Check GitHub issues
- Monitor Firebase analytics
- Test deployment process

**Monthly:**
- Update dependencies
- Test on latest Colab version
- Review and update docs

**As Needed:**
- Security updates
- Bug fixes
- Feature releases

### Dependency Updates

```bash
cd frontend

# Check for updates
npm outdated

# Update dependencies
npm update

# Test thoroughly
npm run build
npm run preview

# Deploy if all good
firebase deploy
```

---

## Versioning

### Semantic Versioning

Follow semver: `MAJOR.MINOR.PATCH`

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

### Release Process

1. Update version in `package.json`
2. Update CHANGELOG.md
3. Create git tag
   ```bash
   git tag -a v1.2.0 -m "Release v1.2.0"
   git push origin v1.2.0
   ```
4. Create GitHub release
5. Deploy frontend
6. Update Colab notebook if needed

---

## Troubleshooting Deployment

### Build Fails

```bash
# Clear cache
rm -rf node_modules dist
npm install
npm run build
```

### Deployment Fails

```bash
# Re-authenticate
firebase login --reauth

# Try deploying again
firebase deploy --only hosting
```

### Colab Notebook Issues

- Ensure all cells run in order
- Check for deprecated libraries
- Test with fresh Colab runtime

---

## Alternative Hosting

### Frontend Alternatives

**Netlify:**
```bash
npm run build
# Drag dist/ folder to Netlify dashboard
```

**Vercel:**
```bash
npm i -g vercel
vercel --prod
```

**GitHub Pages:**
```bash
npm run build
# Push dist/ to gh-pages branch
```

### Backend Alternatives

For advanced users wanting always-on backend:
- Deploy to VPS (DigitalOcean, AWS, etc.)
- Use Docker container
- Set up systemd service
- Configure nginx reverse proxy

Not recommended for general users (loses free Colab benefits).

---

## Next Steps

- Set up monitoring and alerts
- Create deployment scripts
- Document custom domain setup
- Plan backup and disaster recovery

For development deployment, see [Development Guide](./DEVELOPMENT.md).
