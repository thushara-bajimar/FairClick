import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the dashboard runs on :5173 and proxies to the FastAPI backend on :8000.
// In production `npm run build` writes dist/, which the backend serves directly.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/sites': 'http://127.0.0.1:8000',
    },
  },
})
