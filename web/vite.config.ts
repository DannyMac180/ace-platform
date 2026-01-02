import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/playbooks': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/usage': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/billing': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ready': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
