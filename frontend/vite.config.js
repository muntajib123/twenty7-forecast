// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/noaa': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
