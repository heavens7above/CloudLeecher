import axios from 'axios';

// Store API Key in a module-level variable (or could attach to axios defaults)
let currentApiKey = '';

// Create base instance
const api = axios.create({
    timeout: 30000, // Increased to 30s for ngrok reliability
    headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
    },
});

// Request Interceptor to inject API Key
api.interceptors.request.use((config) => {
    if (currentApiKey) {
        config.headers['x-api-key'] = currentApiKey;
    }
    return config;
}, (error) => {
    return Promise.reject(error);
});

export const setApiUrl = (url) => {
    if (url) {
        // Ensure URL doesn't have trailing slash for consistency
        const cleanUrl = url.endsWith('/') ? url.slice(0, -1) : url;
        api.defaults.baseURL = cleanUrl;
    }
};

export const setApiKey = (key) => {
    currentApiKey = key || '';
};

export const TorrentAPI = {
    checkHealth: async () => {
        return api.get('/health');
    },

    addMagnet: async (magnet) => {
        const { data } = await api.post('/api/download/magnet', { magnet });
        return data;
    },

    addTorrentFile: async (base64Content) => {
        const { data } = await api.post('/api/download/file', { torrent: base64Content });
        return data;
    },

    getStatus: async () => {
        return api.get('/api/status');
    },

    pause: async (gid) => {
        return api.post('/api/control/pause', { gid });
    },

    resume: async (gid) => {
        return api.post('/api/control/resume', { gid });
    },

    remove: async (gid) => {
        return api.post('/api/control/remove', { gid });
    },

    getDriveInfo: async () => {
        return api.get('/api/drive/info');
    },

    getLogs: async () => {
        return api.get('/api/logs');
    },

    cleanupAll: async () => {
        return api.post('/api/cleanup');
    }
};

export default api;
