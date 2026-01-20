import React from 'react';

export function Input({
    className = '',
    error = false,
    icon: Icon,
    ...props
}) {
    return (
        <div className="relative">
            {Icon && (
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-400">
                    <Icon size={18} />
                </div>
            )}
            <input
                className={`
          w-full bg-background border rounded-lg py-2.5 text-base text-white placeholder-gray-500 focus:outline-none focus:ring-2 transition-all
          ${Icon ? 'pl-10' : 'pl-3'}
          ${error
                        ? 'border-white focus:border-white focus:ring-white/20'
                        : 'border-white/10 focus:border-white focus:ring-white/20 hover:border-white/20'
                    }
          ${className}
        `}
                {...props}
            />
        </div>
    );
}
