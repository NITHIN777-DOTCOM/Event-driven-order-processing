import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes to dist/. scripts/deploy_frontend.py uploads it to S3 with cache headers:
// hashed files under assets/ are immutable; index.html is no-cache.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true }, // must match the API's CORS allow-list
  build: { outDir: "dist", sourcemap: false },
});
