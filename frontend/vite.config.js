// frontend/vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => {
  // Only enable proxy during `vite dev` (command === 'serve').
  // Use process.env.VITE_API_BASE_URL when available (set in your environment).
  const apiTarget = process.env.VITE_API_BASE_URL || "http://localhost:8000";

  return {
    plugins: [react()],
    // Only provide server.proxy for dev mode so builds don't embed localhost.
    server: command === "serve" ? {
      proxy: {
        "/noaa": {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        },
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          secure: false,
        }
      }
    } : undefined
  };
});
