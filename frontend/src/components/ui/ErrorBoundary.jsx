import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

export class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        console.error("Uncaught error:", error, errorInfo);
        this.setState({ error, errorInfo });
    }

    handleReset = () => {
        this.setState({ hasError: false, error: null, errorInfo: null });
        window.location.reload();
    };

    handleClearCache = () => {
        localStorage.clear();
        window.location.reload();
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen flex items-center justify-center bg-background p-4 text-white font-sans">
                    <div className="max-w-md w-full bg-surface border border-white/10 rounded-2xl p-8 shadow-2xl text-center">
                        <div className="inline-flex p-4 rounded-full bg-white/5 mb-6 text-white">
                            <AlertTriangle size={48} className="opacity-90" />
                        </div>

                        <h1 className="text-2xl font-bold mb-2">Something went wrong</h1>
                        <p className="text-gray-400 mb-8 text-sm leading-relaxed">
                            The application encountered an unexpected error.
                            We've logged the issue and it will be fixed soon.
                        </p>

                        <div className="p-4 bg-black/40 rounded-lg text-left mb-6 overflow-hidden">
                            <code className="text-xs text-red-400 block font-mono">
                                {this.state.error && this.state.error.toString()}
                            </code>
                        </div>

                        <div className="flex gap-3 justify-center">
                            <Button onClick={this.handleReset} variant="primary" className="flex items-center gap-2">
                                <RefreshCw size={16} /> Reload App
                            </Button>
                            <Button onClick={this.handleClearCache} variant="danger" className="text-xs">
                                Hard Reset (Clear Data)
                            </Button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
