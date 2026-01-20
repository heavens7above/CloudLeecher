import React from 'react';

export function Progress({ value = 0, max = 100, variant = 'primary', className = '' }) {
    const percentage = Math.min(100, Math.max(0, (value / max) * 100));

    const variants = {
        primary: 'bg-[#34c759]', // Sober Emerald Green
        success: 'bg-[#34c759]',
        warning: 'bg-[#ffcc00]',
        danger: 'bg-[#ff3b30]',
    };

    return (
        <div className={`h-2 w-full bg-white/5 rounded-full overflow-hidden ${className}`}>
            <div
                className={`h-full transition-all duration-500 ease-out ${variants[variant]}`}
                style={{ width: `${percentage}%` }}
            />
        </div>
    );
}
