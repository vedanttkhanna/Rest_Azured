import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import localSettings from "./local/config.json" with { type: "json" };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${localSettings.port}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("maplibre-gl")) return "maps";
          if (id.includes("recharts")) return "charts";
          if (id.includes("aws-amplify") || id.includes("@aws-amplify"))
            return "auth";
        },
      },
    },
  },
});
