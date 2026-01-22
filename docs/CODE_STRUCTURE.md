# Code Structure

This document explains the organization and structure of the CloudLeecher codebase.

## Repository Layout

```
CloudLeecher/
├── frontend/              # React web application
├── backend/              # Python backend & Colab notebook
├── docs/                 # Documentation
├── .gitignore           # Git ignore rules
├── LICENSE              # MIT License
└── README.md            # Project README
```

---

## Frontend Structure

```
frontend/
├── src/                      # Source code
│   ├── App.jsx              # Root component
│   ├── main.jsx            # Entry point
│   ├── index.css           # Global styles
│   │
│   ├── components/         # Reusable components
│   │   ├── layout/        # Layout components
│   │   │   └── Header.jsx
│   │   └── ui/           # UI primitives
│   │       ├── Button.jsx
│   │       ├── Card.jsx
│   │       ├── ErrorBoundary.jsx
│   │       ├── Input.jsx
│   │       └── Progress.jsx
│   │
│   ├── context/           # React Context
│   │   ├── AppContext.jsx
│   │   └── ToastContext.jsx
│   │
│   ├── features/          # Feature modules
│   │   ├── downloads/
│   │   │   ├── TorrentInput.jsx
│   │   │   └── TaskList.jsx
│   │   └── logs/
│   │       └── BackendLogs.jsx
│   │
│   └── services/          # External services
│       └── api.js         # API client
│
├── public/               # Static assets
│   └── logo.png
│
├── dist/                 # Build output (generated)
│
├── node_modules/         # Dependencies (generated)
│
├── .firebase/            # Firebase config (generated)
├── .firebaserc          # Firebase project
├── firebase.json        # Firebase settings
├── package.json         # Dependencies & scripts
├── package-lock.json    # Locked dependencies
├── vite.config.js       # Vite configuration
├── tailwind.config.js   # Tailwind configuration
├── postcss.config.js    # PostCSS configuration
└── eslint.config.js     # ESLint rules
```

### Directory Purposes

#### `/src/components/`
Reusable UI components that don't belong to specific features.

- **`layout/`**: Page structure components (Header, Footer, etc.)
- **`ui/`**: Generic UI primitives (Button, Input, Card, etc.)

#### `/src/context/`
React Context providers for global state management.

- `AppContext.jsx`: API URL, connection status
- `ToastContext.jsx`: Toast notifications

#### `/src/features/`
Feature-specific components organized by domain.

- **`downloads/`**: Torrent download management
- **`logs/`**: Backend logging

#### `/src/services/`
External service integrations and API clients.

- `api.js`: Axios instance and API methods

---

## Backend Structure

```
backend/
├── app.py                    # Flask application
└── CloudLeecher.ipynb       # Google Colab notebook
```

### app.py

**Structure**:
```python
# Imports
import xmlrpc.client
from flask import Flask, request, jsonify
from flask_cors import CORS
# ...

# Configuration
DOWNLOAD_DIR = "/content/drive/MyDrive/TorrentDownloads"
ARIA2_RPC_URL = "http://localhost:6800/rpc"
# ...

# Helper Functions
def log(level, operation, message, gid=None, extra=None):
    # Logging function
    pass

# Routes
@app.route('/health', methods=['GET'])
def health():
    # Health check endpoint
    pass

@app.route('/api/download/magnet', methods=['POST'])
def add_magnet():
    # Add magnet link
    pass

# ... more routes ...

# Main
if __name__ == "__main__":
    app.run(port=5000)
```

**Route Organization**:
- Health & Info: `/health`, `/api/logs`, `/api/drive/info`
- Downloads: `/api/download/magnet`, `/api/download/file`
- Status: `/api/status`
- Control: `/api/control/pause`, `/api/control/resume`, `/api/control/remove`
- Maintenance: `/api/cleanup`

### CloudLeecher.ipynb

**Notebook Structure**:
```
Cell 1: Mount Google Drive
Cell 2: Install dependencies
Cell 3: Start Aria2 service
Cell 4: Create app.py (%%writefile)
Cell 5: Launch Flask + ngrok
```

**Important**: Cell 4 and `app.py` must stay in sync!

---

## Configuration Files

### package.json

Defines frontend dependencies and scripts:

```json
{
  "scripts": {
    "dev": "vite",              // Development server
    "build": "vite build",      // Production build
    "preview": "vite preview",  // Preview production build
    "lint": "eslint ."          // Run linter
  },
  "dependencies": {
    "react": "^19.2.0",
    "axios": "^1.13.2",
    // ...
  }
}
```

### vite.config.js

Vite build configuration:

```javascript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173
  },
  build: {
    outDir: 'dist'
  }
});
```

### tailwind.config.js

TailwindCSS customization:

```javascript
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}"
  ],
  theme: {
    extend: {
      colors: { /* custom colors */ },
      animation: { /* custom animations */ }
    }
  }
}
```

### firebase.json

Firebase hosting configuration:

```json
{
  "hosting": {
    "public": "dist",
    "rewrites": [
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

---

## Documentation Structure

```
docs/
├── README.md                  # Documentation index
├── QUICK_START.md            # Getting started guide
├── ARCHITECTURE.md           # System architecture
├── API_REFERENCE.md          # REST API documentation
├── FRONTEND_COMPONENTS.md    # Component documentation
├── CODE_STRUCTURE.md         # This file
├── DEVELOPMENT.md            # Development setup
├── DEPLOYMENT.md             # Deployment guide
├── TROUBLESHOOTING.md        # Common issues
├── CONTRIBUTING.md           # Contribution guidelines
└── FAQ.md                    # Frequently asked questions
```

---

## Import Conventions

### Frontend Imports

```javascript
// 1. External dependencies
import React, { useState, useEffect } from 'react';
import axios from 'axios';

// 2. Internal modules
import { useApp } from '../context/AppContext';
import { TorrentAPI } from '../services/api';

// 3. Components
import { Header } from './components/layout/Header';
import { Button } from './components/ui/Button';

// 4. Styles (if needed)
import './styles.css';
```

### Backend Imports

```python
# 1. Standard library
import os
import json
from datetime import datetime

# 2. Third-party
from flask import Flask, request, jsonify
from flask_cors import CORS
import xmlrpc.client

# 3. Local modules (if any)
# from .utils import helper_function
```

---

## Naming Conventions

### Frontend

**Files**:
- Components: PascalCase (`Header.jsx`, `TaskList.jsx`)
- Utilities: camelCase (`api.js`, `helpers.js`)
- Styles: kebab-case (`index.css`)

**Variables**:
- Components: PascalCase (`TaskList`, `TorrentInput`)
- Functions: camelCase (`handleClick`, `fetchData`)
- Constants: UPPER_CASE (`API_URL`, `MAX_RETRIES`)
- React hooks: camelCase with `use` prefix (`useApp`, `useToast`)

### Backend

**Files**:
- Python files: snake_case (`app.py`)
- Notebooks: PascalCase (`CloudLeecher.ipynb`)

**Variables**:
- Functions: snake_case (`add_magnet`, `get_status`)
- Constants: UPPER_CASE (`DOWNLOAD_DIR`, `ARIA2_RPC_URL`)
- Classes: PascalCase (if used)

---

## State Management

### Frontend State

```
Global State (Context)
├── AppContext
│   ├── apiUrl
│   ├── isConnected
│   └── checkConnection()
└── ToastContext
    └── showToast()

Component State (useState)
├── TorrentInput
│   └── magnetLink, isAdding
├── TaskList
│   └── tasks, isLoading
└── Header
    └── showSettings, url
```

### Backend State

**In-Memory**:
- `logs`: deque (last 100 log entries)
- `s`: Aria2 RPC connection

**Persistent**:
- Google Drive: Downloaded files
- `/content/backend_logs.json`: Log file

---

## Data Flow

### Download Addition Flow

```
User Input (Frontend)
    ↓
TorrentInput.handleAddMagnet()
    ↓
TorrentAPI.addMagnet(magnet)
    ↓
axios.post('/api/download/magnet')
    ↓
[ngrok tunnel]
    ↓
Flask: add_magnet()
    ↓
Aria2 RPC: addUri()
    ↓
Return GID
    ↓
Update Frontend State
```

### Status Polling Flow

```
TaskList Component
    ↓
setInterval(2000ms)
    ↓
TorrentAPI.getStatus()
    ↓
axios.get('/api/status')
    ↓
Flask: get_status()
    ↓
Aria2 RPC: tellActive/tellWaiting/tellStopped()
    ↓
Return status data
    ↓
Update tasks state
    ↓
Re-render UI
```

---

## Build Output

### Development Build

```bash
npm run dev
```

**Output**: none (dev server in memory)
**URL**: http://localhost:5173
**Features**: Hot reload, source maps

### Production Build

```bash
npm run build
```

**Output Directory**: `frontend/dist/`
```
dist/
├── index.html           # Entry HTML
├── assets/
│   ├── index-[hash].js   # Bundled JavaScript
│   ├── index-[hash].css  # Bundled CSS
│   └── logo-[hash].png   # Assets
├── favicon.ico
└── logo.png
```

---

## Version Control

### .gitignore

```gitignore
# Frontend
frontend/node_modules/
frontend/dist/
frontend/.firebase/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db

# Environment
.env
.env.local
```

### Branch Strategy

```
main            # Production-ready code
├── develop     # Integration branch (optional)
└── feature/*   # Feature branches
    ├── feature/new-component
    └── feature/api-improvement
```

---

## Dependencies

### Frontend Dependencies

**Core**:
- `react`: UI library
- `react-dom`: React DOM rendering
- `react-router-dom`: Routing (if needed)

**Utilities**:
- `axios`: HTTP client
- `lucide-react`: Icons

**Styling**:
- `tailwindcss`: Utility-first CSS
- `autoprefixer`: CSS vendor prefixes
- `postcss`: CSS processing

**Build Tools**:
- `vite`: Build tool
- `@vitejs/plugin-react`: React plugin

**Dev Tools**:
- `eslint`: Linting
- `@eslint/js`: ESLint config

### Backend Dependencies

**Core**:
- `flask`: Web framework
- `flask-cors`: CORS support

**Integration**:
- `pyngrok`: ngrok tunneling

**System**:
- `aria2c`: Download engine (system package)

---

## Adding New Features

### 1. New Frontend Component

```bash
# Create component file
touch frontend/src/components/ui/NewComponent.jsx
```

Add to appropriate directory based on type:
- UI primitive → `/components/ui/`
- Layout → `/components/layout/`
- Feature → `/features/{feature-name}/`

### 2. New API Endpoint

**Backend (`app.py`)**:
```python
@app.route('/api/new-endpoint', methods=['POST'])
def new_endpoint():
    # Implementation
    pass
```

**Frontend (`services/api.js`)**:
```javascript
export const TorrentAPI = {
    // ... existing methods ...
    newEndpoint: async (data) => {
        return api.post('/api/new-endpoint', data);
    }
};
```

**Don't forget**: Update Cell 4 in Colab notebook!

### 3. New Context Provider

```bash
touch frontend/src/context/NewContext.jsx
```

Add to `App.jsx`:
```jsx
<NewProvider>
  <ExistingProviders>
    <App />
  </ExistingProviders>
</NewProvider>
```

---

For development workflow, see [Development Guide](./DEVELOPMENT.md).
