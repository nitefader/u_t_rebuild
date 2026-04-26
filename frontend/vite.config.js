import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        providers: resolve(__dirname, "providers.html"),
        chart_lab: resolve(__dirname, "chart_lab.html"),
        brokers: resolve(__dirname, "brokers.html"),
        settings: resolve(__dirname, "settings.html")
      }
    }
  },
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true
      }
    }
  }
});
