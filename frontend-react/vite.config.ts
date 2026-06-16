import path from "path";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/chainlit": {
        target: "http://localhost:8500",
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: "http://localhost:8500",
        changeOrigin: true,
        ws: true,
        timeout: 0,
        proxyTimeout: 0,
        secure: false,
      },
      "/user": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/login": {
        target: "http://localhost:8500",
        changeOrigin: true,
        bypass(req) {
          if (req.method === "GET") return req.url;
        },
      },
      "/logout": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/project": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/feedback": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/mcp": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/set-session-cookie": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/files": { 
        target: "http://localhost:8500",
        changeOrigin: true
      },
    },
  },
});
