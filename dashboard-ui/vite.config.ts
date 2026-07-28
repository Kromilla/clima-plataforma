import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        // 127.0.0.1 y no 'localhost' a propósito: Node 17+ resuelve 'localhost'
        // a ::1 (IPv6) primero, pero uvicorn escucha solo en IPv4 por defecto.
        // Con 'localhost' el proxy falla con "Failed to fetch" aunque la API esté
        // corriendo perfectamente.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
