import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  // One .env for the whole repo: VITE_* keys live in the root .env / .env.example.
  envDir: '..',
  server: {
    port: 5173,
    strictPort: true,
    // Same-origin /api in development, matching the nginx reverse proxy in Phase 8.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
});
