import { defineConfig, loadEnv } from 'vite';
import { readFileSync } from 'node:fs';
import { resolve, parse, join } from 'node:path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  // Backend secrets stay inside this Node process; never define/expose them to the browser bundle.
  const backendEnv = loadEnv(mode, resolve('backend'), '');
  const dbPath = parse(resolve(backendEnv.BUDGETPLUS_DB || 'backend/data/budgetplus.sqlite3'));
  const localKeyPath = join(dbPath.dir, dbPath.name + '.local-api-key');
  return { plugins: [react(), tailwindcss()], server: { host:'0.0.0.0', port:5173, strictPort:true,
    proxy: { '/api': { target:'http://127.0.0.1:8000', configure(proxy) {
      proxy.on('proxyReq', request => {
        request.removeHeader('x-budgetplus-local');
        try { request.setHeader('x-budgetplus-local', readFileSync(localKeyPath, 'utf8').trim()); } catch { /* Backend may still be starting. */ }
      });
    } } }
  } };
});
