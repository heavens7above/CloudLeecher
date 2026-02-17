import axios from 'axios';

// Create base instance but allow updating URL dynamically
const api = axios.create({
    timeout: 30000, // Increased to 30s for ngrok reliability
    headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
    },
});

export const setApiUrl = (url, apiKey = null) => {
    if (url) {
        // Ensure URL doesn't have trailing slash for consistency
        const cleanUrl = url.endsWith('/') ? url.slice(0, -1) : url;
        api.defaults.baseURL = cleanUrl;
    }
    if (apiKey) {
        api.defaults.headers.common['x-api-key'] = apiKey;
    } else {
        delete api.defaults.headers.common['x-api-key'];
    }
};

// Deprecated but kept for compatibility if needed (wraps new config)
export const setApiUrl = (url) => setApiConfig(url, null);

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
