import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the React dev server (port 5173) forwards /api calls to the Python backend (port 8000),
// so the browser only ever talks to one origin and no CORS tricks are needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
