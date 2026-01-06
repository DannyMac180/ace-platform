import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Only proxy API requests (not browser navigation requests for HTML)
const apiProxy = {
  target: 'http://localhost:8000',
  changeOrigin: true,
  // Only proxy if the request accepts JSON (API calls), not HTML (browser navigation)
  bypass: (req: { headers: { accept?: string } }) => {
    if (req.headers.accept?.includes('text/html')) {
      // Return the path to serve index.html for SPA routing
      return '/index.html';
    }
    // Return undefined to proceed with proxy
    return undefined;
  },
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth': apiProxy,
      '/playbooks': apiProxy,
      '/usage': apiProxy,
      '/billing': apiProxy,
      '/health': apiProxy,
      '/ready': apiProxy,
    },
  },
})
