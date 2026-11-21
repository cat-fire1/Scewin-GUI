import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: './',
  plugins: [react(), {
    name: 'desktop-development-csp',
    apply: 'serve',
    transformIndexHtml: html => html.replace(
      "script-src 'self' 'unsafe-eval'",
      "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
    ),
  }],
  server: { host: '127.0.0.1', strictPort: true },
});
