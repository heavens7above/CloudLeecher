import React from 'react';

export function Card({ children, className = '' }) {
    return (
        <div className={`bg-black/40 border border-white/10 rounded-xl shadow-xl backdrop-blur-xl ${className}`}>
            {children}
        </div>
    );
}

export function CardHeader({ children, className = '' }) {
    return (
        <div className={`p-4 border-b border-white/5 ${className}`}>
            {children}
        </div>
    );
}

export function CardTitle({ children, className = '' }) {
    return (
        <h3 className={`text-lg font-semibold text-white flex items-center gap-2 ${className}`}>
            {children}
        </h3>
    );
}

export function CardContent({ children, className = '' }) {
    return (
        <div className={`p-4 ${className}`}>
            {children}
        </div>
    );
}
