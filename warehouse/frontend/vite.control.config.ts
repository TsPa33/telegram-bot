import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dedicated preview/runtime: no customer Warehouse HTML entry.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist-control",
    rollupOptions: { input: { control: "control/index.html" } },
  },
});
