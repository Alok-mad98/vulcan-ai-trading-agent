import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/",
  server: { port: 5174, proxy: { "/api": "https://vulcan-dashboard.arechampionw.workers.dev" } },
});
