import react from '@vitejs/plugin-react'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'

// The dev server proxies the Django API so session and CSRF cookies stay same-origin.
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  build: {
    // Two pages: the staff app (/) and the public customer website (/site/).
    rollupOptions: {
      input: { app: resolve(__dirname, 'index.html'), site: resolve(__dirname, 'site/index.html') },
    },
  },
  server: {
    proxy: {
      '/api': { target: apiTarget },
      '/admin': { target: apiTarget },
      '/static': { target: apiTarget },
    },
  },
})
