import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The production build is written straight into the proxy package, which serves it at /dashboard.
export default defineConfig({
  plugins: [react()],
  base: '/dashboard/',
  // Recharts makes the bundle ~600 kB; that is fine for a tool served from localhost.
  build: { outDir: '../proxy/static', emptyOutDir: true, chunkSizeWarningLimit: 900 },
  server: {
    port: 5173,
    // `npm run dev` talks to the proxy running on :8000
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
