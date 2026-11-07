import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// `base: './'` lets the build live under /app/ (how bot/api.py serves it) or anywhere else.
// /api is proxied to `python tools/devserver.py 8080`, so dev + preview exercise the real backend contract.
const proxy = { '/api': 'http://localhost:8080' };

export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
  build: { outDir: 'dist', sourcemap: false, target: 'es2019' },
});
