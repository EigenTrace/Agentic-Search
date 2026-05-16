/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: '#0a0a0f',
          panel: '#11121a',
          subtle: '#161824',
        },
        accent: {
          DEFAULT: '#3b82f6',
          dim: '#1d4ed8',
        },
        conf: {
          high: '#22c55e',
          medium: '#f59e0b',
          low: '#6b7280',
          unverified: '#a78bfa',
        },
      },
      fontFamily: {
        sans: ['Geist', 'Instrument Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      animation: {
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'slide-in': 'slideIn 200ms ease-out',
      },
      keyframes: {
        pulseSoft: {
          '0%, 100%': { opacity: 1 },
          '50%': { opacity: 0.55 },
        },
        slideIn: {
          '0%': { transform: 'translateX(100%)', opacity: 0 },
          '100%': { transform: 'translateX(0)', opacity: 1 },
        },
      },
    },
  },
  plugins: [],
};
