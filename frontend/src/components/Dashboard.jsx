import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { HardDrive, DownloadCloud, Activity, Clock, CheckCircle } from 'lucide-react';
import AddDownload from './AddDownload';
import DownloadList from './DownloadList';

const StatsCard = ({ title, value, subtext, icon: Icon, color }) => (
    <div className="bg-surface rounded-xl p-5 border border-slate-700/50 shadow-sm relative overflow-hidden">
        <div className={`absolute -right-4 -top-4 w-24 h-24 bg-${color}-500/10 rounded-full blur-2xl`}></div>
        <div className="relative z-10 flex justify-between items-start">
            <div>
                <p className="text-slate-400 text-sm font-medium mb-1">{title}</p>
                <h3 className="text-2xl font-bold text-white tracking-tight">{value}</h3>
                {subtext && <p className="text-xs text-slate-500 mt-1">{subtext}</p>}
            </div>
            <div className={`p-3 bg-slate-700/30 rounded-lg text-${color}-400`}>
                <Icon className="w-6 h-6" />
            </div>
        </div>
    </div>
);

const Dashboard = ({ apiUrl }) => {
    const [data, setData] = useState({ active: [], waiting: [], stopped: [] });
    const [driveInfo, setDriveInfo] = useState({ total: 0, used: 0, free: 0 });
    const [loading, setLoading] = useState(true);
    const intervalRef = useRef(null);

    const fetchData = async () => {
        try {
            const headers = {
                'ngrok-skip-browser-warning': 'true',
                'Bypass-Tunnel-Reminder': 'true'
            };
            const [statusRes, driveRes] = await Promise.all([
                axios.get(`${apiUrl}/api/status`, { headers }),
                axios.get(`${apiUrl}/api/drive/info`, { headers })
            ]);
            setData(statusRes.data);
            setDriveInfo(driveRes.data);
            setLoading(false);
        } catch (e) {
            console.error("Fetch error", e);
        }
    };

    useEffect(() => {
        fetchData();
        intervalRef.current = setInterval(fetchData, 2000); // 2-second poll
        return () => clearInterval(intervalRef.current);
    }, [apiUrl]);

    const formatBytes = (bytes) => {
        if (!bytes) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    // Calculate total download speed
    const totalSpeed = data.active?.reduce((acc, curr) => acc + parseInt(curr.downloadSpeed), 0) || 0;

    return (
        <div className="space-y-6 animate-in fade-in duration-500">

            {/* Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <StatsCard
                    title="Drive Storage"
                    value={formatBytes(driveInfo.free)}
                    subtext={`${formatBytes(driveInfo.used)} used of ${formatBytes(driveInfo.total)}`}
                    icon={HardDrive}
                    color="blue"
                />
                <StatsCard
                    title="Active Downloads"
                    value={data.active?.length || 0}
                    subtext={`${data.waiting?.length || 0} queued`}
                    icon={Activity}
                    color="accent"
                />
                <StatsCard
                    title="Global Speed"
                    value={`${formatBytes(totalSpeed)}/s`}
                    subtext="Current downstream"
                    icon={DownloadCloud}
                    color="emerald"
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left Column: Upload */}
                <div className="lg:col-span-1 space-y-6">
                    <AddDownload apiUrl={apiUrl} onAdd={fetchData} />

                    <div className="bg-blue-500/5 border border-blue-500/10 rounded-lg p-4 text-sm text-blue-300">
                        <h4 className="font-semibold mb-1 flex items-center gap-2">
                            <HardDrive className="w-4 h-4" />
                            Storage Path
                        </h4>
                        <p className="opacity-80">Files are saved to: <br /> <code className="bg-blue-500/20 px-1 py-0.5 rounded text-xs">MyDrive/TorrentDownloads</code></p>
                    </div>
                </div>

                {/* Right Column: Lists */}
                <div className="lg:col-span-2 space-y-8 pb-10">
                    <div className="bg-surface rounded-xl border border-slate-700 p-6 min-h-[400px]">
                        <h2 className="text-xl font-bold mb-6 flex items-center gap-2 border-b border-slate-700 pb-4">
                            <DownloadCloud className="w-6 h-6 text-primary" />
                            Download Queue
                        </h2>

                        <div className="space-y-8">
                            {(!data.active?.length && !data.waiting?.length && !data.stopped?.length) && (
                                <div className="text-center py-10 text-slate-500">
                                    <DownloadCloud className="w-12 h-12 mx-auto mb-3 opacity-20" />
                                    <p>No downloads yet.</p>
                                </div>
                            )}

                            <DownloadList
                                title="Active"
                                items={data.active}
                                apiUrl={apiUrl}
                                icon={Activity}
                                onAction={fetchData}
                            />

                            <DownloadList
                                title="Waiting"
                                items={data.waiting}
                                apiUrl={apiUrl}
                                icon={Clock}
                                onAction={fetchData}
                            />

                            <DownloadList
                                title="Completed / Stopped"
                                items={data.stopped}
                                apiUrl={apiUrl}
                                icon={CheckCircle}
                                onAction={fetchData}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Dashboard;
