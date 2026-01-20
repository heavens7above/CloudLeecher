import React, { useState, useCallback } from 'react';
import { Magnet, Upload, Link, Loader2 } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { useToast } from '../../context/ToastContext';
import { Card, CardContent } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export function TorrentInput() {
    const { addMagnet, addTorrentFile, isConnected } = useApp();
    const { addToast } = useToast();
    const [link, setLink] = useState('');
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('magnet');
    const fileInputRef = React.useRef(null);
    const [isDragging, setIsDragging] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!link) return;

        setLoading(true);
        try {
            await addMagnet(link);
            setLink('');
            addToast('Magnet link added', 'success');
        } catch (err) {
            console.error(err);
            addToast('Failed to add magnet link', 'error');
        } finally {
            setLoading(false);
        }
    };

    const handleFile = async (file) => {
        if (!file.name.endsWith('.torrent')) {
            addToast('Please select a valid .torrent file', 'error');
            return;
        }

        setLoading(true);
        const reader = new FileReader();

        reader.onload = async (event) => {
            try {
                const base64Content = event.target.result.split(',')[1];
                await addTorrentFile(base64Content);
                addToast(`Added torrent file: ${file.name}`, 'success');
                setActiveTab('magnet');
            } catch (err) {
                console.error('Torrent upload error:', err);
                const msg = err.response?.data?.error || err.message;
                addToast(`Upload failed: ${msg}`, 'error');
            } finally {
                setLoading(false);
            }
        };

        reader.onerror = () => {
            setLoading(false);
            addToast('Failed to read file', 'error');
        };

        reader.readAsDataURL(file);
    };

    const onFileSelect = (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleFile(e.target.files[0]);
        }
    };

    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleDrop = useCallback(async (e) => {
        e.preventDefault();
        setIsDragging(false);

        const files = e.dataTransfer.files;
        if (files.length === 0) return;
        handleFile(files[0]);
    }, [addMagnet]);

    return (
        <Card className="mb-8 overflow-hidden">
            <div className="flex border-b border-white/5">
                <button
                    className={`flex-1 min-w-0 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${activeTab === 'magnet' ? 'bg-emerald-500/10 text-emerald-500 border-b-2 border-emerald-500' : 'text-gray-400 hover:text-white hover:bg-white/5'
                        }`}
                    onClick={() => setActiveTab('magnet')}
                >
                    <Link size={16} className="shrink-0" /> <span className="truncate">Magnet Link</span>
                </button>
                <button
                    className={`flex-1 min-w-0 py-3 text-sm font-medium flex items-center justify-center gap-2 transition-colors ${activeTab === 'file' ? 'bg-emerald-500/10 text-emerald-500 border-b-2 border-emerald-500' : 'text-gray-400 hover:text-white hover:bg-white/5'
                        }`}
                    onClick={() => setActiveTab('file')}
                >
                    <Upload size={16} className="shrink-0" /> <span className="truncate">.torrent File</span>
                </button>
            </div>

            <CardContent>
                {activeTab === 'magnet' ? (
                    <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-2">
                        <div className="flex-1">
                            <Input
                                icon={Magnet}
                                placeholder="Paste magnet link here..."
                                value={link}
                                onChange={(e) => setLink(e.target.value)}
                                disabled={!isConnected || loading}
                            />
                        </div>
                        <Button type="submit" loading={loading} disabled={!isConnected || !link} className="bg-white text-black hover:bg-emerald-400 hover:text-black transition-colors w-full sm:w-auto">
                            {loading ? 'Adding...' : 'Download'}
                        </Button>
                    </form>
                ) : (
                    <div
                        className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer ${isDragging ? 'border-emerald-500 bg-emerald-500/10' : 'border-white/10 hover:border-white/20 hover:bg-white/5'
                            }`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            className="hidden"
                            accept=".torrent"
                            onChange={onFileSelect}
                        />
                        <div className="flex flex-col items-center gap-3 text-gray-400">
                            <Upload size={32} />
                            <p className="text-sm font-medium">Drag & Drop .torrent file here</p>
                            <span className="text-xs text-gray-500">or click to browse</span>
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
