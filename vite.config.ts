import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: {
    '/api': { target: 'http://127.0.0.1:8000', ws: true },
    '/stream': {
      target: 'http://127.0.0.1:8889', rewrite: path => path.replace(/^\/stream/, ''),
      configure: proxy => proxy.on('proxyRes', response => {
        if (response.headers.location?.startsWith('/')) response.headers.location = `/stream${response.headers.location}`;
      }),
    },
  } },
  build: { outDir: 'dist' },
});
