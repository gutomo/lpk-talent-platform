import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// /api is proxied to the backend on 8001 (8000 is used by the voice-ai-tutor demo).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8001",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
