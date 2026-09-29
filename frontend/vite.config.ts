import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The built UI is served by the Python backend (excel_filler/desktop/server.py).
// For `npm run dev`, start the backend with `excel-filler-desktop --browser`, then set
// BACKEND=http://127.0.0.1:<port> so /api and /ws are proxied to it.
const backend = process.env.BACKEND ?? 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../excel_filler/desktop/static', emptyOutDir: true },
  server: {
    proxy: {
      '/api': backend,
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
    },
  },
})
