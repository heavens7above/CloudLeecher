import React, { createContext, useContext, useState, useCallback } from 'react';
import { X, CheckCircle, AlertCircle, Info } from 'lucide-react';

const ToastContext = createContext();

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);

    const addToast = useCallback((message, type = 'info', duration = 5000) => {
        const id = Date.now().toString();
        setToasts((prev) => [...prev, { id, message, type }]);

        if (duration > 0) {
            setTimeout(() => {
                removeToast(id);
            }, duration);
        }
    }, []);

    const removeToast = useCallback((id) => {
        setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, []);

    return (
        <ToastContext.Provider value={{ addToast, removeToast }}>
            {children}
            <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
                {toasts.map((toast) => (
                    <div
                        key={toast.id}
                        className={`
              pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg shadow-2xl border backdrop-blur-md min-w-[300px] animate-slide-up
              ${toast.type === 'success' ? 'bg-black/80 border-white/20 text-white' : ''}
              ${toast.type === 'error' ? 'bg-black/90 border-white text-white' : ''}
              ${toast.type === 'info' ? 'bg-black/80 border-white/10 text-gray-200' : ''}
            `}
                    >
                        {toast.type === 'success' && <CheckCircle size={18} className="text-white" />}
                        {toast.type === 'error' && <AlertCircle size={18} className="text-white" />}
                        {toast.type === 'info' && <Info size={18} className="text-gray-400" />}

                        <p className="text-sm font-medium flex-1">{toast.message}</p>

                        <button
                            onClick={() => removeToast(toast.id)}
                            className="opacity-50 hover:opacity-100 transition-opacity"
                        >
                            <X size={14} />
                        </button>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

export const useToast = () => useContext(ToastContext);
