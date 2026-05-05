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
      },
      "/user": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/login": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
      "/logout": {
        target: "http://localhost:8500",
        changeOrigin: true,
      },
    },
  },
});
