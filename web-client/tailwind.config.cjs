/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
      },
      borderRadius: {
        xl2: '1.25rem',
      },
      boxShadow: {
        aceternity: '0 18px 60px rgba(15, 23, 42, 0.10)',
        glow: '0 0 48px rgba(59, 130, 246, 0.22)',
      },
      animation: {
        shimmer: 'shimmer 2.2s linear infinite',
        spotlight: 'spotlight 5s ease .75s 1 forwards',
      },
      keyframes: {
        shimmer: {
          from: { backgroundPosition: '0 0' },
          to: { backgroundPosition: '-200% 0' },
        },
        spotlight: {
          '0%': { opacity: 0, transform: 'translate(-72%, -62%) scale(.7)' },
          '100%': { opacity: 1, transform: 'translate(-50%, -42%) scale(1)' },
        },
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
};
