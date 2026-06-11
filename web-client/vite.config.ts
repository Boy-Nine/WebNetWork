import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  build: {
    chunkSizeWarningLimit: 1300,
    rollupOptions: {
      output: {
        manualChunks: {
          antd: ['antd', '@ant-design/icons'],
          motion: ['framer-motion'],
          vendor: ['axios', 'dayjs'],
        },
      },
      onwarn(warning, warn) {
        if (warning.message?.includes('Module level directives') && warning.message?.includes('use client')) return;
        warn(warning);
      },
    },
  },
});
