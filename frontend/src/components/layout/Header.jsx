import React, { useState } from 'react';
import { Activity, Wifi, WifiOff, HardDrive, Settings, LogOut } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export function Header() {
    const { isConnected, apiUrl, apiKey, setApiUrl, setApiKey, driveInfo, checkConnection, disconnect } = useApp();
    const [showSettings, setShowSettings] = useState(!apiUrl);
    const [tempUrl, setTempUrl] = useState(apiUrl);
    const [tempKey, setTempKey] = useState(apiKey);

    const handleSaveUrl = () => {
        setApiKey(tempKey); // Update Key first
        setApiUrl(tempUrl); // Then URL (triggers connection check)
        setShowSettings(false);
    };

    const formatBytes = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    return (
        <div className="bg-black/20 border-b border-white/5 backdrop-blur-md sticky top-0 z-50 overflow-hidden">
            <div className="max-w-7xl mx-auto px-2 sm:px-4 py-3">
                <div className="flex items-center justify-between gap-2">
                    {/* Logo and Title */}
                    <a href="/" className="flex items-center gap-2 sm:gap-4 shrink-0 hover:opacity-80 transition-opacity">
                        <div className="h-9 w-9 relative shrink-0">
                            <img src="/logo.png" alt="CloudLeecher" className="w-full h-full object-contain opacity-90" />
                        </div>
                        <h1 className="text-lg font-bold text-white tracking-wide">
                            CloudLeecher
                        </h1>
                    </a>

                    {/* Settings Icon - Always visible in top right */}
                    {!showSettings && (
                        <div className="flex items-center gap-2">
                            {isConnected && (
                                <Button variant="ghost" size="icon" onClick={disconnect} className="text-gray-400 hover:text-red-400" title="Disconnect">
                                    <LogOut size={18} />
                                </Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => setShowSettings(true)} className="text-gray-400 hover:text-white" title="Settings">
                                <Settings size={18} />
                            </Button>
                        </div>
                    )}
                </div>

                {/* Second Row: Status, Links, and Settings Panel */}
                <div className="flex flex-col gap-3 mt-3">
                    {/* Status Indicators - visible on md+ */}
                    <div className="flex items-center gap-4 text-xs font-medium text-gray-500">
                        {isConnected ? (
                            <span className="flex items-center gap-1.5 text-emerald-500"><div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" /> Online</span>
                        ) : (
                            <span className="flex items-center gap-1.5 text-gray-600 cursor-pointer hover:text-white transition-colors" onClick={checkConnection}>
                                <div className="w-1.5 h-1.5 bg-gray-600 rounded-full" /> Disconnected
                            </span>
                        )}
                        {isConnected && (
                            <>
                                <span className="w-px h-3 bg-white/10"></span>
                                <span className="flex items-center gap-1.5"><HardDrive size={12} /> {formatBytes(driveInfo.free)} Free</span>
                            </>
                        )}
                    </div>

                    {/* Colab and Ngrok Links - Now visible on mobile */}
                    <div className="flex items-center gap-2 flex-wrap">
                        <a
                            href="https://colab.research.google.com/drive/1j-L-CXE-ObYWZ-_qGv0uNlpRsS3HPQSE?usp=sharing"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs font-medium text-orange-400 hover:text-orange-300 transition-colors"
                        >
                            Open Colab ↗
                        </a>
                        <span className="text-gray-700">•</span>
                        <a
                            href="https://dashboard.ngrok.com/authtokens"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs font-medium text-blue-400 hover:text-blue-300 transition-colors"
                        >
                            Ngrok Auth ↗
                        </a>
                    </div>

                    {/* Settings Panel */}
                    {showSettings && (
                        <div className="flex flex-col gap-2 animate-fade-in">
                            <Input
                                value={tempUrl}
                                onChange={(e) => setTempUrl(e.target.value)}
                                placeholder="Enter Ngrok Public URL"
                                className="w-full text-sm bg-black/50"
                            />
                             <Input
                                value={tempKey}
                                onChange={(e) => setTempKey(e.target.value)}
                                placeholder="Enter API Key (from Colab output)"
                                className="w-full text-sm bg-black/50"
                                type="password"
                            />
                            <div className="flex gap-2">
                                <Button size="sm" onClick={handleSaveUrl} className="bg-white text-black hover:bg-gray-200 flex-1">Connect</Button>
                                <Button size="sm" variant="ghost" onClick={() => setShowSettings(false)} className="flex-1">Cancel</Button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
