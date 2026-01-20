import React from 'react';
import axios from 'axios';
import { Play, Pause, Trash2, File, Folder, Download, CheckCircle, Clock } from 'lucide-react';

const formatSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const getProgress = (completed, total) => {
    if (total == 0) return 0;
    return ((completed / total) * 100).toFixed(1);
};

const DownloadItem = ({ item, apiUrl, onAction }) => {
    // Try to determine a name
    let name = 'Unknown';
    if (item.files && item.files.length > 0) {
        const path = item.files[0].path;
        if (path) {
            name = path.split('/').pop();
        } else if (item.placeholders && item.placeholders.name) {
            // bit of a long shot for simple aria2 response
            name = "Loading Metadata...";
        }
    }
    // Fallback if path is empty (metadata download)
    if (name === 'Unknown' && item.totalLength == 0) name = "Fetching Metadata...";

    const progress = getProgress(item.completedLength, item.totalLength);
    const isComplete = item.status === 'complete';
    const isPaused = item.status === 'paused';

    const handleControl = async (action) => {
        try {
            await axios.post(`${apiUrl}/api/control/${action}`, { gid: item.gid }, {
                headers: {
                    'ngrok-skip-browser-warning': 'true',
                    'Bypass-Tunnel-Reminder': 'true'
                }
            });
            onAction();
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="bg-surface/50 border border-slate-700/50 rounded-lg p-4 hover:border-primary/30 transition-all group">
            <div className="flex justify-between items-start mb-3">
                <div className="flex items-center gap-3 overflow-hidden">
                    <div className="bg-slate-700 p-2 rounded-lg">
                        {isComplete ? <CheckCircle className="w-5 h-5 text-emerald-400" /> : <File className="w-5 h-5 text-blue-400" />}
                    </div>
                    <div>
                        <h4 className="font-medium truncate  max-w-[200px] md:max-w-md" title={name}>{name}</h4>
                        <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
                            <span className="bg-slate-700/50 px-2 py-0.5 rounded text-slate-300">{formatSize(item.totalLength)}</span>
                            {item.status === 'active' && (
                                <span className="text-emerald-400">{formatSize(item.downloadSpeed)}/s</span>
                            )}
                            <span className="capitalize">{item.status}</span>
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity">
                    {item.status === 'active' && (
                        <button onClick={() => handleControl('pause')} className="p-2 hover:bg-slate-700 rounded-lg text-slate-300">
                            <Pause className="w-4 h-4" />
                        </button>
                    )}
                    {item.status === 'paused' && (
                        <button onClick={() => handleControl('resume')} className="p-2 hover:bg-slate-700 rounded-lg text-slate-300">
                            <Play className="w-4 h-4" />
                        </button>
                    )}
                    <button onClick={() => handleControl('remove')} className="p-2 hover:bg-red-500/20 text-slate-300 hover:text-red-400 rounded-lg">
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div className="relative h-2 bg-slate-700 rounded-full overflow-hidden">
                <div
                    className={`absolute top-0 left-0 h-full transition-all duration-300 ${isComplete ? 'bg-emerald-500' : isPaused ? 'bg-amber-500' : 'bg-primary'}`}
                    style={{ width: `${progress}%` }}
                ></div>
            </div>
            <div className="text-right text-xs text-slate-500 mt-1">{progress}%</div>
        </div>
    );
};

const DownloadList = ({ title, items, apiUrl, icon: Icon, onAction }) => {
    if (!items || items.length === 0) return null;

    return (
        <div className="space-y-3">
            <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider flex items-center gap-2">
                {Icon && <Icon className="w-4 h-4" />}
                {title} ({items.length})
            </h3>
            <div className="space-y-3">
                {items.map(item => (
                    <DownloadItem key={item.gid} item={item} apiUrl={apiUrl} onAction={onAction} />
                ))}
            </div>
        </div>
    );
};

export default DownloadList;
