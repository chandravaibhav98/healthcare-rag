import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Paths the SPA calls on the API. In development Vite proxies them (same origin, so the
// refresh-token cookie works); in Phase 8 nginx does the same in front of the API.
const API_PATHS = ['/api', '/version', '/readyz', '/healthz'];
const API_TARGET = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // One .env for the whole repo: VITE_* keys live in the root .env / .env.example.
  envDir: '..',
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, API_TARGET])),
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: Object.fromEntries(API_PATHS.map((path) => [path, API_TARGET])),
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        // Charts are only used on admin pages; keep them out of the assistant's bundle.
        manualChunks(id) {
          if (id.includes('node_modules/recharts') || id.includes('node_modules/d3-')) {
            return 'charts';
          }
          // Long-lived vendor chunks change rarely, so browsers keep them cached across deploys.
          if (/node_modules\/(react|react-dom|react-router|scheduler)\//.test(id)) return 'react';
          if (/node_modules\/(zod|react-hook-form|@hookform)\//.test(id)) return 'forms';
          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    css: false,
    coverage: { provider: 'v8', include: ['src/**'], exclude: ['src/api/generated/**'] },
  },
});
