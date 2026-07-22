import path from "path";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import { nodePolyfills } from "vite-plugin-node-polyfills";

const CHAINLIT_TARGET = process.env.VITE_CHAINLIT_SERVER || "http://localhost:8500";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    nodePolyfills({ include: ["events"] }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5150,
    watch: {
      usePolling: true,
      interval: 100,
    },
    proxy: {
      "/chainlit": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
        ws: true,
      },
      "/ws": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
        ws: true,
        timeout: 0,
        proxyTimeout: 0,
        secure: false,
      },
      "/user": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/login": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
        bypass(req) {
          if (req.method === "GET") return req.url;
        },
      },
      "/logout": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/project": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/auth": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/feedback": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/mcp": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/set-session-cookie": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      "/files": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
      // IFC (and other) static assets served by the Chainlit API:
      // /public/ifc-data/{id}/{file}.ifc
      "/public": {
        target: CHAINLIT_TARGET,
        changeOrigin: true,
      },
    },
  },
});
