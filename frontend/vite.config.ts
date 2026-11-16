import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const alvo = process.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: alvo, changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: false },
});
