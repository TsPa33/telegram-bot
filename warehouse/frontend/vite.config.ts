import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {rollupOptions: {input: {warehouse: "index.html", control: "control/index.html"}}},
  server: {
    proxy: {
      "/api": {
        target: process.env.WAREHOUSE_API_PROXY || "http://127.0.0.1:8010",
      },
      "/health": {
        target: process.env.WAREHOUSE_API_PROXY || "http://127.0.0.1:8010",
      },
    },
  },
});
