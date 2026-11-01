import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base defaults to "/" for local dev; set VITE_BASE_PATH="/repo-name/" when
// building for a GitHub Pages project sub-path. Every data/pmtiles URL in
// the app is built from import.meta.env.BASE_URL (derived from this), so
// nothing needs to change elsewhere when the base path changes.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || "/",
  // maplibre-gl loads its renderer in a Web Worker via a dynamic
  // `new URL(..., import.meta.url)`, which esbuild's dependency
  // pre-bundling does not resolve correctly (the worker chunk 504s,
  // so the map never renders). Excluding it from pre-bundling serves
  // it as native ESM instead, which resolves the worker URL correctly.
  optimizeDeps: { exclude: ["maplibre-gl"] },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
  },
});
