# Development Setup

This guide will help you set up a local development environment for CloudLeecher.

## Prerequisites

Before you begin, ensure you have:

- **Node.js** (v18 or higher)
- **npm** (v9 or higher)
- **Python** (v3.8 or higher)
- **Git**
- A code editor (VS Code recommended)
- A Google account (for Colab testing)

---

## Repository Structure

```
CloudLeecher/
├── frontend/              # React web application
│   ├── src/              # Source code
│   ├── public/           # Static assets
│   ├── dist/             # Build output
│   ├── package.json      # Dependencies
│   └── vite.config.js    # Build configuration
├── backend/              # Python backend
│   ├── app.py           # Flask application
│   └── CloudLeecher.ipynb  # Colab notebook
├── docs/                # Documentation
├── README.md           # Project README
└── LICENSE             # MIT License
```

---

## Frontend Development

### 1. Clone the Repository

```bash
git clone https://github.com/heavens7above/CloudLeecher.git
cd CloudLeecher/frontend
```

### 2. Install Dependencies

```bash
npm install
```

This installs:
- React 19.2.0
- Vite 7.2.4
- TailwindCSS 3.4.17
- Axios 1.13.2
- React Router DOM 7.12.0
- Lucide React 0.562.0

### 3. Start Development Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

### 4. Build for Production

```bash
npm run build
```

Production files will be in `frontend/dist/`

### 5. Preview Production Build

```bash
npm run preview
```

---

## Frontend Project Structure

```
frontend/src/
├── App.jsx                 # Main application component
├── main.jsx               # Entry point
├── index.css             # Global styles + Tailwind imports
│
├── components/           # Reusable components
│   ├── layout/
│   │   └── Header.jsx          # App header with settings
│   └── ui/
│       ├── Button.jsx          # Button component
│       ├── Card.jsx            # Card container
│       ├── ErrorBoundary.jsx   # Error handling
│       ├── Input.jsx           # Input field
│       └── Progress.jsx        # Progress bar
│
├── context/              # React Context providers
│   ├── AppContext.jsx         # Global app state
│   └── ToastContext.jsx       # Toast notifications
│
├── features/             # Feature modules
│   ├── downloads/
│   │   ├── TorrentInput.jsx   # Add magnet/file input
│   │   └── TaskList.jsx       # Download task list
│   └── logs/
│       └── BackendLogs.jsx    # Backend log viewer
│
└── services/             # External services
    └── api.js                 # Axios API client
```

---

## Backend Development

### Local Testing (Without Colab)

For testing backend changes locally before deploying to Colab:

#### 1. Install Python Dependencies

```bash
cd backend
pip install flask flask-cors
```

#### 2. Install Aria2

**macOS:**
```bash
brew install aria2
```

**Ubuntu/Debian:**
```bash
sudo apt-get install aria2
```

**Windows:**
Download from [aria2 releases](https://github.com/aria2/aria2/releases)

#### 3. Start Aria2 RPC

```bash
aria2c --enable-rpc \
       --rpc-listen-all=true \
       --rpc-allow-origin-all \
       --dir=./downloads \
       --daemon=true
```

#### 4. Run Flask Backend

```bash
python app.py
```

Backend will run on `http://localhost:5000`

#### 5. Test API

```bash
curl http://localhost:5000/health
# Should return: {"status":"ok","service":"CloudLeecher-Backend"}
```

---

## Colab Notebook Development

### 1. Make a Copy

- Open [CloudLeecher.ipynb](https://colab.research.google.com/drive/1j-L-CXE-ObYWZ-_qGv0uNlpRsS3HPQSE?usp=sharing)
- Click **File → Save a copy in Drive**

### 2. Edit the Notebook

Edit cells directly in Colab, or:

```bash
# Download notebook
# Edit locally (use Jupyter)
# Re-upload to Colab
```

### 3. Sync Changes

Keep `backend/CloudLeecher.ipynb` and `backend/app.py` in sync:

- The notebook's Cell 4 generates `app.py` via `%%writefile`
- When updating `app.py`, also update Cell 4 in the notebook
- Both should have identical backend logic

---

## Development Workflow

### Making Changes to Frontend

1. **Create a Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Edit files in `frontend/src/`
   - Hot reload will show changes immediately

3. **Test Locally**
   - Test with local backend (port 5000)
   - Or test with Colab backend (ngrok URL)

4. **Update API URL for Development**
   ```javascript
   // In frontend/src/services/api.js
   // Temporarily set a default URL for testing
   const api = axios.create({
       baseURL: 'http://localhost:5000', // or ngrok URL
       timeout: 30000,
       headers: {
           'Content-Type': 'application/json',
           'ngrok-skip-browser-warning': 'true',
       },
   });
   ```

5. **Build and Test**
   ```bash
   npm run build
   npm run preview
   ```

### Making Changes to Backend

1. **Edit `backend/app.py`**

2. **Test Locally**
   ```bash
   python app.py
   ```

3. **Update Notebook**
   - Copy changes to Cell 4 of `CloudLeecher.ipynb`
   - Test in Colab

4. **Verify Both Match**
   ```bash
   # Ensure app.py and notebook Cell 4 are in sync
   ```

---

## Code Style Guide

### Frontend (JavaScript/React)

```javascript
// Use functional components
function Component() {
  return <div>Content</div>;
}

// Use hooks
const [state, setState] = useState(initialValue);
const value = useContext(MyContext);

// Props destructuring
function Button({ label, onClick, disabled }) {
  return <button onClick={onClick} disabled={disabled}>{label}</button>;
}

// TailwindCSS for styling
<div className="flex items-center gap-4 p-4 bg-surface rounded-xl">

// Async/await for API calls
async function fetchData() {
  try {
    const response = await api.get('/endpoint');
    return response.data;
  } catch (error) {
    console.error('Error:', error);
  }
}
```

### Backend (Python)

```python
# Follow PEP 8
# Use type hints where helpful
def add_download(magnet: str) -> dict:
    return {"status": "success", "gid": gid}

# Use try/except for error handling
try:
    result = s.aria2.addUri([magnet])
    log("info", "add_magnet", "Success", gid=result)
    return result
except Exception as e:
    log("error", "add_magnet", f"Failed: {str(e)}")
    raise

# Log important operations
log(level, operation, message, gid=None, extra=None)
```

---

## Testing

### Frontend Testing

```bash
# Run linter
npm run lint

# Type checking (if using TypeScript in future)
# npm run type-check
```

### Backend Testing

```bash
# Test API endpoints manually
curl http://localhost:5000/health
curl -X POST http://localhost:5000/api/download/magnet \
  -H "Content-Type: application/json" \
  -d '{"magnet": "magnet:?xt=urn:btih:TEST"}'

# Check Aria2 RPC
curl http://localhost:6800/jsonrpc \
  -d '{"jsonrpc":"2.0","id":"1","method":"aria2.getVersion"}'
```

### Integration Testing

1. Start local backend
2. Start frontend dev server
3. Test full flow: add magnet → poll status → remove

---

## Debugging

### Frontend Debugging

**Browser DevTools:**
```javascript
// Enable detailed logging
localStorage.setItem('debug', 'true');

// React DevTools for component inspection
// Install: https://chrome.google.com/webstore/detail/react-developer-tools/
```

**Network Tab:**
- Monitor API calls
- Check request/response payloads
- Verify ngrok headers

### Backend Debugging

**Flask Debug Mode:**
```python
# In app.py, change:
app.run(port=5000, debug=True)
```

**Logging:**
```python
# Use the log() function for structured logging
log("info", "operation_name", "Debug message", extra={"key": "value"})

# Check logs endpoint
# GET /api/logs returns recent log entries
```

---

## Environment Variables

### Frontend

Create `frontend/.env.local`:
```bash
# Optional: Set default API URL for development
VITE_API_URL=http://localhost:5000
```

Use in code:
```javascript
const API_URL = import.meta.env.VITE_API_URL || '';
```

### Backend

For Colab, use Colab Secrets.

For local development:
```bash
# No environment variables needed
# Aria2 runs on localhost:6800 by default
```

---

## Deployment

### Frontend (Firebase)

```bash
cd frontend

# Build
npm run build

# Deploy (requires Firebase CLI)
firebase deploy
```

### Backend (Colab)

1. Update `backend/CloudLeecher.ipynb`
2. Upload to Google Drive
3. Share notebook (optional)
4. Users run notebook cells

---

## Common Development Tasks

### Adding a New API Endpoint

1. **Backend (`app.py`):**
   ```python
   @app.route('/api/new-endpoint', methods=['POST'])
   def new_endpoint():
       data = request.json
       # Process data
       log("info", "new_endpoint", "Processing...")
       return jsonify({"result": "success"})
   ```

2. **Frontend (`services/api.js`):**
   ```javascript
   export const TorrentAPI = {
       // ... existing methods ...
       
       newEndpoint: async (data) => {
           return api.post('/api/new-endpoint', data);
       }
   };
   ```

3. **Use in Component:**
   ```javascript
   import { TorrentAPI } from '../services/api';
   
   async function handleAction() {
       const result = await TorrentAPI.newEndpoint({ key: 'value' });
       console.log(result.data);
   }
   ```

### Adding a New UI Component

```bash
# Create component file
touch frontend/src/components/ui/NewComponent.jsx
```

```javascript
// frontend/src/components/ui/NewComponent.jsx
export function NewComponent({ prop1, prop2 }) {
    return (
        <div className="p-4 bg-surface rounded-xl">
            {/* Component content */}
        </div>
    );
}
```

```javascript
// Use in App.jsx or feature component
import { NewComponent } from './components/ui/NewComponent';

<NewComponent prop1="value" prop2={data} />
```

---

## Recommended VS Code Extensions

- **ESLint** - JavaScript linting
- **Prettier** - Code formatting
- **Tailwind CSS IntelliSense** - TailwindCSS autocomplete
- **ES7+ React/Redux/React-Native snippets** - React snippets
- **Python** - Python support
- **Pylance** - Python language server

---

## Resources

- [React Documentation](https://react.dev/)
- [Vite Documentation](https://vitejs.dev/)
- [TailwindCSS Documentation](https://tailwindcss.com/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Aria2 Documentation](https://aria2.github.io/)
- [axios Documentation](https://axios-http.com/)

---

## Next Steps

- Read [Architecture Overview](./ARCHITECTURE.md) to understand the system
- Check [API Reference](./API_REFERENCE.md) for endpoint details
- See [Contributing Guidelines](./CONTRIBUTING.md) for contribution process
