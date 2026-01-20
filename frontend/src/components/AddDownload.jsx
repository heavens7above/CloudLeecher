import React, { useState } from 'react';
import axios from 'axios';
import { Magnet, Link, Plus } from 'lucide-react';

const AddDownload = ({ apiUrl, onAdd }) => {
    const [magnet, setMagnet] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!magnet) return;

        setLoading(true);
        try {
            await axios.post(`${apiUrl}/api/download/magnet`, { magnet }, {
                headers: {
                    'ngrok-skip-browser-warning': 'true',
                    'Bypass-Tunnel-Reminder': 'true'
                }
            });
            setMagnet('');
            onAdd(); // Trigger refresh
        } catch (err) {
            alert('Failed to add download');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-surface rounded-xl border border-slate-700 p-6 shadow-sm">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Magnet className="w-5 h-5 text-accent" />
                Add New Download
            </h3>

            <form onSubmit={handleSubmit} className="flex gap-3">
                <div className="relative flex-1">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Link className="h-5 w-5 text-slate-500" />
                    </div>
                    <input
                        type="text"
                        className="block w-full pl-10 bg-background border border-slate-600 rounded-lg py-2.5 px-4 text-slate-200 placeholder-slate-600 focus:ring-2 focus:ring-accent focus:border-transparent outline-none transition-all"
                        placeholder="Paste magnet link here..."
                        value={magnet}
                        onChange={(e) => setMagnet(e.target.value)}
                    />
                </div>
                <button
                    type="submit"
                    disabled={loading || !magnet}
                    className="bg-accent hover:bg-amber-600 text-white font-medium py-2.5 px-6 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-amber-500/20"
                >
                    {loading ? 'Adding...' : <><Plus className="w-4 h-4" /> Add</>}
                </button>
            </form>
        </div>
    );
};

export default AddDownload;
