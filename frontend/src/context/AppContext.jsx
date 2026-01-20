import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { setApiUrl, TorrentAPI } from '../services/api';
import { useToast } from './ToastContext';

const AppContext = createContext();

export function AppProvider({ children }) {
    const { addToast } = useToast();
    // --- Persistent Settings ---
    const [apiUrl, setApiUrlState] = useState(() => localStorage.getItem('CL_API_URL') || '');
    const [tasks, setTasks] = useState(() => JSON.parse(localStorage.getItem('CL_TASKS') || '[]'));

    // --- Runtime State ---
    const [isConnected, setIsConnected] = useState(false);
    const [driveInfo, setDriveInfo] = useState({ total: 0, free: 0, used: 0 });
    const [lastUpdated, setLastUpdated] = useState(null);

    // --- Refs for Locks & Ghost Prevention ---
    const interactionInProgress = useRef(false); // Lock for connection attempts
    const ignoredTaskIds = useRef(new Set()); // Blacklist for deleted tasks (Ghost Killer)

    // Update Axios and LocalStorage when URL changes
    useEffect(() => {
        localStorage.setItem('CL_API_URL', apiUrl);
        setApiUrl(apiUrl);
        if (apiUrl) checkConnection();
    }, [apiUrl]);

    // Persist Tasks when they change
    useEffect(() => {
        localStorage.setItem('CL_TASKS', JSON.stringify(tasks));
    }, [tasks]);

    // Polling Loop
    useEffect(() => {
        if (!apiUrl || !isConnected) return;

        const interval = setInterval(async () => {
            try {
                await refreshStatus();
            } catch (err) {
                console.error('Polling failed:', err);
            }
        }, 3000);

        return () => clearInterval(interval);
    }, [apiUrl, isConnected]);

    const checkConnection = async () => {
        // Debounce / Lock to prevent "Ghost Server" multiple connects
        if (interactionInProgress.current) {
            console.log("Connection attempt ignored - already in progress");
            return;
        }
        interactionInProgress.current = true;

        let retries = 3;
        let lastError;
        let success = false;

        for (let i = 0; i < retries; i++) {
            try {
                await TorrentAPI.checkHealth();
                if (!isConnected) addToast("Connected to Backend", "success");
                setIsConnected(true);
                success = true;
                break; // Connected!
            } catch (err) {
                lastError = err;
                console.error(`Connection attempt ${i + 1}/${retries} failed:`, err);
                if (i < retries - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
                }
            }
        }

        if (!success) {
            console.error('Connection failed after retries:', lastError);
            if (isConnected) addToast("Connection Lost. Check your backend.", "error");
            setIsConnected(false);
        }

        interactionInProgress.current = false; // Release lock
        return success;
    };

    const disconnect = () => {
        setApiUrlState('');
        setIsConnected(false);
        addToast("Disconnected from Backend", "info");
    };

    const refreshStatus = async () => {
        const [statusRes, driveRes] = await Promise.all([
            TorrentAPI.getStatus(),
            TorrentAPI.getDriveInfo()
        ]);

        // Validate and Parse Drive Info Safely
        const safeDriveInfo = {
            total: parseInt(driveRes.data?.total) || 0,
            free: parseInt(driveRes.data?.free) || 0,
            used: parseInt(driveRes.data?.used) || 0
        };
        setDriveInfo(safeDriveInfo);
        setLastUpdated(new Date());

        updateTasksFromBackend(statusRes.data);
    };

    const updateTasksFromBackend = (backendData) => {
        // DEBUG: See what the backend is actually sending
        // console.log("CloudLeecher Backend Response:", backendData); 

        const { active, waiting, stopped } = backendData;

        // Create a map of all backend tasks for quick lookup
        const backendTasksMap = new Map();
        [...active, ...waiting, ...stopped].forEach(t => backendTasksMap.set(t.gid, t));

        // CLEANUP: Remove IDs from ignored list if they are truly gone from backend
        // This keeps our blacklist small
        for (const ignoredGid of ignoredTaskIds.current) {
            if (!backendTasksMap.has(ignoredGid)) {
                ignoredTaskIds.current.delete(ignoredGid);
            }
        }

        setTasks(currentTasks => {
            const newTasks = [...currentTasks];

            for (let i = 0; i < newTasks.length; i++) {
                const localTask = newTasks[i];

                // If this task is on our kill list, FORCE remove it locally and skip update
                if (ignoredTaskIds.current.has(localTask.gid)) {
                    // We mark it as removed, but ideally we should filter it out?
                    // Let's mark as 'removed' status so UI can filter if needed, 
                    // or we can just NOT update it.
                    // IMPORTANT: If we want it gone, we should probably ensure it stays 'removed'.
                    newTasks[i] = { ...localTask, status: 'removed', speed: 0 };
                    continue;
                }

                const backendTask = backendTasksMap.get(localTask.gid);

                if (backendTask) {
                    // Update existing
                    let newStatus = backendTask.status;
                    let newName = backendTask.files?.[0]?.path?.split('/').pop() || localTask.name || 'Unknown File';

                    // DEBUG: Detect if backend explicitly removes it
                    if (newStatus === 'removed') {
                        console.warn(`Task ${localTask.gid} returned as 'removed' by backend.`);
                        newStatus = 'error'; // Force visible
                        if (!newName.startsWith('[Server Removed]')) {
                            newName = `[Server Removed] ${newName}`;
                        }
                    }

                    newTasks[i] = {
                        ...localTask,
                        name: newName,
                        size: parseInt(backendTask.totalLength) || 0,
                        completed: parseInt(backendTask.completedLength) || 0,
                        speed: parseInt(backendTask.downloadSpeed) || 0,
                        status: newStatus,
                        progress: (parseInt(backendTask.completedLength) / parseInt(backendTask.totalLength)) * 100 || 0,
                        timestamp: new Date().toISOString()
                    };
                    backendTasksMap.delete(localTask.gid);
                } else {
                    // Task MISSING from backend
                    // Check Grace Period: If task was added < 60 seconds ago, KEEP IT
                    // This handles latency between adding task and backend reporting it.
                    // Increased to 60s to handle slow Colab/Backend sync.
                    const taskTime = new Date(localTask.timestamp || 0).getTime();
                    const now = new Date().getTime();
                    const isYoung = (now - taskTime) < 60000; // 60 seconds grace

                    if (isYoung && localTask.status === 'active') {
                        // Keep it as is (don't remove)
                        // Maybe update status to 'initializing' to let user know?
                        // For now, keep as 'active' (Resolving metadata...)
                    } else if (localTask.status !== 'removed') {
                        // Mark as ERROR if it's old and missing, so we can see it failed
                        console.warn(`Task ${localTask.gid} missing from backend response. Marking as error.`);
                        newTasks[i] = {
                            ...localTask,
                            status: 'error',
                            name: localTask.name.startsWith('[Lost]') ? localTask.name : `[Lost] ${localTask.name}`,
                            speed: 0
                        };
                    }
                }
            }

            // Add NEW tasks (unless ignored)
            backendTasksMap.forEach((bTask) => {
                if (ignoredTaskIds.current.has(bTask.gid)) return; // Don't re-add ghosts

                console.log("New task detected from backend:", bTask.gid, bTask.name); // DEBUG
                newTasks.unshift({
                    gid: bTask.gid,
                    name: bTask.files?.[0]?.path?.split('/').pop() || 'Unknown Task',
                    size: parseInt(bTask.totalLength) || 0,
                    completed: parseInt(bTask.completedLength) || 0,
                    speed: parseInt(bTask.downloadSpeed) || 0,
                    status: bTask.status,
                    progress: (parseInt(bTask.completedLength) / parseInt(bTask.totalLength)) * 100 || 0,
                    timestamp: new Date().toISOString()
                });
            });

            return newTasks;
        });
    };

    const addMagnet = async (magnet) => {
        try {
            const res = await TorrentAPI.addMagnet(magnet);

            if (!res || !res.gid) {
                console.error("Invalid response from addMagnet:", res);
                addToast("Failed to add task: Invalid backend response", "error");
                return;
            }

            setTasks(prev => [{
                gid: res.gid,
                name: 'Resolving metadata...',
                size: 0,
                completed: 0,
                speed: 0,
                status: 'active',
                progress: 0,
                timestamp: new Date().toISOString()
            }, ...prev]);
            return res;
        } catch (err) {
            console.error("Add magnet failed:", err);
            addToast("Failed to add magnet link", "error");
            throw err;
        }
    };

    const addTorrentFile = async (base64Content) => {
        try {
            const res = await TorrentAPI.addTorrentFile(base64Content);

            if (!res || !res.gid) {
                console.error("Invalid response from addTorrentFile:", res);
                addToast("Failed to add task: Invalid backend response", "error");
                return;
            }

            setTasks(prev => [{
                gid: res.gid,
                name: 'Uploading torrent file...',
                size: 0,
                completed: 0,
                speed: 0,
                status: 'active',
                progress: 0,
                timestamp: new Date().toISOString()
            }, ...prev]);
            return res;
        } catch (err) {
            console.error("Add torrent file failed:", err);
            addToast("Failed to add torrent file", "error");
            throw err;
        }
    };

    const removeTask = async (gid) => {
        // 1. Add to Ignore List (Ghost Killer)
        ignoredTaskIds.current.add(gid);

        // 2. Optimistic Update - Remove immediately from list
        setTasks(prev => prev.filter(t => t.gid !== gid));

        try {
            await TorrentAPI.remove(gid);
        } catch (err) {
            console.error("Failed to remove task:", err);
        }
    };

    const pauseTask = async (gid) => {
        setTasks(prev => prev.map(t => t.gid === gid ? { ...t, status: 'paused', speed: 0 } : t));
        await TorrentAPI.pause(gid);
    };

    const resumeTask = async (gid) => {
        setTasks(prev => prev.map(t => t.gid === gid ? { ...t, status: 'waiting' } : t));
        await TorrentAPI.resume(gid);
    };

    const clearHistory = () => {
        const tasksToRemove = tasks.filter(t =>
            t.status !== 'active' &&
            t.status !== 'waiting' &&
            t.status !== 'paused'
        );

        setTasks(prev => prev.filter(t =>
            t.status === 'active' ||
            t.status === 'waiting' ||
            t.status === 'paused'
        ));

        tasksToRemove.forEach(t => {
            // Also ignore them so they don't come back while removing
            ignoredTaskIds.current.add(t.gid);
            TorrentAPI.remove(t.gid).catch(err => console.error("Failed to clear task from backend:", t.gid, err));
        });
    };

    return (
        <AppContext.Provider value={{
            apiUrl, setApiUrl: setApiUrlState,
            isConnected, checkConnection, disconnect,
            tasks, addMagnet, addTorrentFile, removeTask, pauseTask, resumeTask, clearHistory,
            driveInfo, lastUpdated
        }}>
            {children}
        </AppContext.Provider>
    );
}

export const useApp = () => useContext(AppContext);
