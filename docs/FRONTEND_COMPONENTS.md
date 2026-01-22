# Frontend Components Documentation

This document provides detailed information about the frontend components in CloudLeecher.

## Component Hierarchy

```
App
├── ToastProvider (Context)
└── AppProvider (Context)
    └── CloudLeecherApp
        ├── Header
        └── Main Content
            ├── TorrentInput (if connected)
            ├── TaskList
            └── BackendLogs
```

---

## Core Components

### App.jsx

**Purpose**: Root component that wraps the app with context providers

**Structure**:
```jsx
function App() {
  return (
    <ToastProvider>
      <AppProvider>
        <CloudLeecherApp />
      </AppProvider>
    </ToastProvider>
  );
}
```

**Components**:
- `CloudLeecherApp`: Main application UI
- Wrapped with `ToastProvider` and `AppProvider` for state management

---

### CloudLeecherApp

**Purpose**: Main application layout and routing logic

**State**:
```javascript
const { apiUrl, isConnected } = useApp();
```

**Features**:
- Displays welcome screen when no API URL configured
- Shows warning when backend check fails
- Renders main interface when connected
- Includes header, main content, and footer

**Layout**:
```jsx
<div className="min-h-screen">
  <Header />
  <main>
    {!apiUrl ? <WelcomeScreen /> : <MainInterface />}
  </main>
  <footer>...</footer>
</div>
```

---

## Layout Components

### Header (`components/layout/Header.jsx`)

**Purpose**: Top navigation bar with branding and settings

**Features**:
- App logo and title
- Connection status indicator
- Settings modal for API URL configuration
- Backend health check

**State**:
```javascript
const [showSettings, setShowSettings] = useState(false);
const [url, setUrl] = useState('');
const { apiUrl, setApiUrl, isConnected, checkConnection } = useApp();
```

**Key Functions**:
- `handleConnect()`: Validates and sets API URL
- `handleDisconnect()`: Clears API URL
- Periodic health checks

**UI Indicators**:
- 🟢 Green dot: Connected
- 🔴 Red dot: Disconnected
- ⚙️ Settings icon: Opens settings modal

---

## UI Primitive Components

### Button (`components/ui/Button.jsx`)

**Purpose**: Reusable button component with variants

**Props**:
```typescript
{
  children: ReactNode,
  variant?: 'primary' | 'secondary' | 'danger',
  size?: 'sm' | 'md' | 'lg',
  disabled?: boolean,
  onClick?: () => void,
  className?: string
}
```

**Variants**:
- `primary`: Blue accent button
- `secondary`: Gray outline button
- `danger`: Red destructive button

**Usage**:
```jsx
<Button variant="primary" onClick={handleClick}>
  Download
</Button>
```

---

### Card (`components/ui/Card.jsx`)

**Purpose**: Container component for grouping content

**Props**:
```typescript
{
  children: ReactNode,
  className?: string,
  padding?: 'none' | 'sm' | 'md' | 'lg'
}
```

**Styling**:
- Background with glass morphism effect
- Rounded corners
- Border with subtle glow

**Usage**:
```jsx
<Card>
  <h2>Task Details</h2>
  <p>Content here...</p>
</Card>
```

---

### Input (`components/ui/Input.jsx`)

**Purpose**: Styled text input field

**Props**:
```typescript
{
  value: string,
  onChange: (value: string) => void,
  placeholder?: string,
  type?: 'text' | 'url' | 'file',
  disabled?: boolean,
  error?: string
}
```

**Features**:
- Error state styling
- Focus animations
- Disabled state
- Placeholder support

**Usage**:
```jsx
<Input
  value={magnetLink}
  onChange={setMagnetLink}
  placeholder="Paste magnet link or .torrent file"
  error={error}
/>
```

---

### Progress (`components/ui/Progress.jsx`)

**Purpose**: Progress bar for download visualization

**Props**:
```typescript
{
  value: number,        // 0-100
  max?: number,         // default: 100
  color?: string,       // Tailwind color class
  showLabel?: boolean,  // Show percentage
  size?: 'sm' | 'md' | 'lg'
}
```

**Features**:
- Animated fill
- Gradient background
- Optional percentage label
- Responsive sizing

**Usage**:
```jsx
<Progress 
  value={downloadProgress} 
  color="green" 
  showLabel 
/>
```

---

### ErrorBoundary (`components/ui/ErrorBoundary.jsx`)

**Purpose**: Catches and displays JavaScript errors gracefully

**Features**:
- Prevents entire app crash
- Shows user-friendly error message
- Logs error to console
- Optional error reporting

**Usage**:
```jsx
<ErrorBoundary>
  <YourComponent />
</ErrorBoundary>
```

---

## Feature Components

### TorrentInput (`features/downloads/TorrentInput.jsx`)

**Purpose**: Input interface for adding torrents

**State**:
```javascript
const [magnetLink, setMagnetLink] = useState('');
const [isAdding, setIsAdding] = useState(false);
```

**Features**:
- Magnet link input field
- .torrent file upload
- Input validation
- Loading state during add

**Functions**:
- `handleAddMagnet()`: Adds magnet link via API
- `handleFileUpload()`: Handles .torrent file upload
- `validateInput()`: Validates magnet link format

**File Upload Flow**:
```javascript
1. User selects .torrent file
2. Read file as base64
3. Send to backend via API
4. Display result
```

---

### TaskList (`features/downloads/TaskList.jsx`)

**Purpose**: Displays and manages download tasks

**State**:
```javascript
const [tasks, setTasks] = useState({ active: [], waiting: [], stopped: [] });
const [isLoading, setIsLoading] = useState(true);
```

**Features**:
- Real-time status polling (2-second interval)
- Task categorization (active, waiting, stopped)
- Per-task controls (pause, resume, remove)
- GID transition tracking

**Polling Logic**:
```javascript
useEffect(() => {
  const interval = setInterval(async () => {
    const status = await TorrentAPI.getStatus();
    setTasks(status.data);
  }, 2000);
  
  return () => clearInterval(interval);
}, []);
```

**Task Card Display**:
- File name
- Progress bar
- Download speed
- ETA
- Seeder count
- Control buttons

---

### BackendLogs (`features/logs/BackendLogs.jsx`)

**Purpose**: Displays recent backend operation logs

**State**:
```javascript
const [logs, setLogs] = useState([]);
const [expanded, setExpanded] = useState(false);
```

**Features**:
- Collapsible log viewer
- Color-coded log levels (info, warning, error)
- Auto-refresh
- Timestamp display

**Log Entry Format**:
```javascript
{
  timestamp: "2026-01-22T17:30:15.123456",
  level: "info",
  operation: "add_magnet",
  message: "Magnet link added successfully",
  gid: "1234567890abcdef",
  extra: { ... }
}
```

---

## Context Providers

### AppContext (`context/AppContext.jsx`)

**Purpose**: Global application state management

**State**:
```javascript
{
  apiUrl: string | null,
  setApiUrl: (url: string) => void,
  isConnected: boolean,
  checkConnection: () => Promise<boolean>
}
```

**Features**:
- API URL persistence (localStorage)
- Backend connection status
- Health check function

**Usage**:
```javascript
import { useApp } from '../context/AppContext';

function Component() {
  const { apiUrl, isConnected } = useApp();
  // ...
}
```

---

### ToastContext (`context/ToastContext.jsx`)

**Purpose**: Toast notification system

**State**:
```javascript
{
  showToast: (message: string, type: 'success' | 'error' | 'info') => void
}
```

**Features**:
- Auto-dismiss after 3 seconds
- Stacking notifications
- Color-coded by type
- Slide-in animation

**Usage**:
```javascript
import { useToast } from '../context/ToastContext';

function Component() {
  const { showToast } = useToast();
  
  const handleSuccess = () => {
    showToast('Download added!', 'success');
  };
}
```

---

## Styling System

### TailwindCSS Configuration

**Custom Colors**:
```javascript
colors: {
  primary: '#4285F4',
  surface: 'rgba(255, 255, 255, 0.05)',
  accent: '#34A853',
  warning: '#FBBC04',
  error: '#EA4335'
}
```

**Custom Utilities**:
```css
.glass {
  @apply bg-white/5 backdrop-blur-lg border border-white/10;
}

.animate-fade-in {
  animation: fadeIn 0.3s ease-in;
}

.animate-slide-up {
  animation: slideUp 0.4s ease-out;
}
```

---

## Responsive Design

### Breakpoints

- `sm`: 640px and up
- `md`: 768px and up
- `lg`: 1024px and up
- `xl`: 1280px and up

### Mobile-First Approach

```jsx
<div className="
  flex-col           /* Mobile: stack vertically */
  md:flex-row        /* Desktop: horizontal layout */
  gap-4              /* Consistent spacing */
  p-4 md:p-8        /* Larger padding on desktop */
">
```

---

## Performance Optimizations

### Code Splitting

- React.lazy for route-based splitting
- Dynamic imports for heavy components

### Memoization

```javascript
import { useMemo, useCallback } from 'react';

const sortedTasks = useMemo(() => {
  return tasks.sort((a, b) => a.timestamp - b.timestamp);
}, [tasks]);

const handleClick = useCallback(() => {
  // Handler logic
}, [dependencies]);
```

### Debouncing

```javascript
const debouncedSearch = useMemo(
  () => debounce(handleSearch, 300),
  []
);
```

---

## Accessibility

### Keyboard Navigation

- All interactive elements are keyboard accessible
- Tab order follows visual flow
- Focus indicators visible

### ARIA Labels

```jsx
<button aria-label="Remove download">
  <IconTrash />
</button>
```

### Semantic HTML

- Use proper heading hierarchy
- `<main>`, `<header>`, `<footer>` tags
- `<button>` vs `<div onClick>`

---

## Component Best Practices

### 1. Single Responsibility
Each component has one clear purpose

### 2. Props Validation
Use PropTypes or TypeScript

### 3. Error Handling
Wrap API calls in try/catch

### 4. Loading States
Show loading indicators for async operations

### 5. Empty States
Handle no-data scenarios gracefully

---

## Future Component Ideas

- **DownloadHistory**: Persistent download history
- **Settings**: More configuration options
- **ThemeToggle**: Dark/light theme switcher
- **NotificationSettings**: Configure alerts
- **FileManager**: Browse Drive files
- **SearchBar**: Filter/search torrents

---

For implementation details, see [Development Guide](./DEVELOPMENT.md).
