import React from 'react';
import { Play, Pause, Trash2, File, CheckCircle, AlertCircle, Clock, Download, UploadCloud, Check } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { Card, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Progress } from '../../components/ui/Progress';

export function TaskList() {
    const { tasks, clearHistory } = useApp();

    // Filter out removed/ghost tasks for display
    // DEBUG: Show ALL tasks to debug disappearance
    const visibleTasks = tasks; // .filter(t => t.status !== 'removed');

    if (visibleTasks.length === 0) {
        return (
            <div className="text-center py-12 text-gray-500 animate-fade-in">
                <div className="inline-flex p-4 rounded-full bg-surface mb-4">
                    <Download size={32} className="opacity-50" />
                </div>
                <p className="text-lg font-medium text-gray-400">No downloads yet</p>
                <p className="text-sm">Add a magnet link to start leaching.</p>
            </div>
        );
    }

    return (
        <div className="space-y-4 animate-slide-up">
            <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-white">Active Tasks</h2>
                {visibleTasks.length > 0 && (
                    <Button variant="ghost" size="sm" onClick={clearHistory} className="text-xs">
                        Clear History
                    </Button>
                )}
            </div>
            <div className="grid gap-4">
                {visibleTasks.map((task) => (
                    <TaskCard key={task.gid} task={task} />
                ))}
            </div>
        </div>
    );
}

function DebugPanel({ visibleTasks }) {
    const { lastUpdated, tasks, backendGids } = useApp();
    const [isOpen, setIsOpen] = React.useState(false);

    return (
        <div className="mt-8 border-t border-white/10 pt-4">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-2"
            >
                {isOpen ? 'Hide Debug Info' : 'Show Debug Info'}
            </button>

            {isOpen && (
                <div className="mt-4 p-4 bg-black/50 rounded text-xs font-mono text-gray-400 overflow-x-auto space-y-2">
                    <p>Last Updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : 'Never'}</p>
                    <p>Total Local Tasks: {tasks.length}</p>
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <strong className="text-white">Local GIDs:</strong>
                            <pre className="mt-1 text-emerald-400">
                                {JSON.stringify(tasks.map(t => ({ gid: t.gid, status: t.status })), null, 2)}
                            </pre>
                        </div>
                        <div>
                            <strong className="text-white">Backend GIDs:</strong>
                            <pre className="mt-1 text-blue-400">
                                {JSON.stringify(backendGids, null, 2)}
                            </pre>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function TaskCard({ task }) {
    const { pauseTask, resumeTask, removeTask } = useApp();

    const getStatusColor = (status) => {
        switch (status) {
            case 'active': return 'text-white';
            case 'moving': return 'text-yellow-400';
            case 'saved': return 'text-emerald-400';
            case 'complete': return 'text-gray-400'; // Dimmed for completed (aria2 sense)
            case 'error': return 'text-white underline decoration-wavy decoration-white/30'; // Underlined for error
            case 'paused': return 'text-gray-500'; // Very dimmed for paused
            case 'removed': return 'text-red-900 line-through opacity-50'; // DEBUG: Removed tasks
            default: return 'text-gray-600';
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'active': return <ActivityIcon />;
            case 'moving': return <UploadCloud size={16} className="text-yellow-400 animate-pulse" />;
            case 'saved': return <CheckCircle size={16} className="text-emerald-400" />;
            case 'complete': return <Check size={16} className="text-gray-400" />;
            case 'error': return <AlertCircle size={16} className="text-white" />;
            case 'paused': return <Pause size={16} />;
            default: return <Clock size={16} />;
        }
    };

    const formatSize = (bytes) => {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    const formatSpeed = (speed) => {
        if (!speed || speed == 0) return '';
        return `${formatSize(speed)}/s`;
    };

    return (
        <Card className={`hover:border-emerald-500/30 transition-colors overflow-hidden ${task.status === 'saved' ? 'border-emerald-500/20 bg-emerald-900/5' : ''}`}>
            <CardContent className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
                <div className={`p-3 rounded-lg bg-white/5 border border-white/5 ${getStatusColor(task.status)} shrink-0`}>
                    {task.status === 'active' ? <LoaderIcon /> :
                     task.status === 'moving' ? <UploadCloud size={24} className="animate-bounce" /> :
                     task.status === 'saved' ? <CheckCircle size={24} /> :
                     <File size={24} />}
                </div>

                <div className="flex-1 min-w-0 w-full">
                    <div className="flex items-center justify-between mb-1 gap-2">
                        <h4 className="font-medium text-white truncate flex-1">{task.name}</h4>
                        <span className={`text-xs font-semibold uppercase tracking-wider ${getStatusColor(task.status)} shrink-0`}>
                            {task.status}
                        </span>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between text-xs text-gray-400 mb-2 gap-1">
                        <span>
                            {task.size && task.size > 0
                                ? `${formatSize(task.completed)} / ${formatSize(task.size)}`
                                : 'Fetching metadata...'}
                        </span>
                        {task.speed > 0 && <span>{formatSpeed(task.speed)}</span>}
                        {(task.seeds > 0 || task.peers > 0) && (
                            <span className="text-gray-500 ml-2">
                                Seeds: {task.seeds} | Peers: {task.peers}
                            </span>
                        )}
                        {task.errorMessage && (
                            <div className="text-red-400 text-xs mt-1 w-full break-all">
                                Error: {task.errorMessage}
                            </div>
                        )}
                    </div>

                    <Progress value={task.progress} className={task.status === 'moving' ? 'bg-yellow-900/20' : ''} indicatorClassName={task.status === 'moving' ? 'bg-yellow-500' : task.status === 'saved' ? 'bg-emerald-500' : ''} />
                </div>

                <div className="flex items-center gap-2 w-full sm:w-auto justify-end sm:pl-2">
                    {task.status === 'active' && (
                        <Button
                            variant="secondary"
                            size="icon"
                            onClick={() => pauseTask(task.gid)}
                            className="min-w-[44px] min-h-[44px] sm:min-w-[36px] sm:min-h-[36px]"
                        >
                            <Pause size={16} />
                        </Button>
                    )}
                    {task.status === 'paused' && (
                        <Button
                            className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 min-w-[44px] min-h-[44px] sm:min-w-[36px] sm:min-h-[36px]"
                            size="icon"
                            onClick={() => resumeTask(task.gid)}
                        >
                            <Play size={16} />
                        </Button>
                    )}
                    <Button
                        variant="danger"
                        size="icon"
                        onClick={() => removeTask(task.gid)}
                        className="min-w-[44px] min-h-[44px] sm:min-w-[36px] sm:min-h-[36px]"
                    >
                        <Trash2 size={16} />
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}

const ActivityIcon = () => (
    <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
    </svg>
)

const LoaderIcon = () => (
    <div className="animate-pulse">
        <Download size={24} />
    </div>
)
