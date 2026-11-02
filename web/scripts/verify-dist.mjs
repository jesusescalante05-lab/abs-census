// Post-build check (ADR-006 "Production bug: MapLibre worker 404"): the
// maplibre-gl worker file has repeatedly been silently dropped from
// dist/assets/ (Rollup can't statically detect its runtime-computed URL,
// so nothing emits it unless maplibregl.setWorkerUrl() is wired up in
// MapView.jsx). A missing worker file does not fail `vite build` -- the
// app just 404s on it in the browser -- so this has to be checked
// separately, right after the build, not relied on to surface itself.

import { readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const assetsDir = fileURLToPath(new URL("../dist/assets", import.meta.url));

let files;
try {
  files = readdirSync(assetsDir);
} catch (err) {
  console.error(`verify-dist: could not read ${assetsDir} (did you run \`npm run build\` first?): ${err.message}`);
  process.exit(1);
}

const workerFile = files.find((f) => f.startsWith("maplibre-gl-worker"));

if (!workerFile) {
  console.error(
    `verify-dist: FAIL -- no maplibre-gl-worker* file in dist/assets/ (found: ${files.join(", ") || "(empty)"}). ` +
      "The map will 404 fetching its worker in production. " +
      "Check MapView.jsx still imports maplibre-gl/dist/maplibre-gl-worker.mjs?url and calls maplibregl.setWorkerUrl() before any Map is created.",
  );
  process.exit(1);
}

console.log(`verify-dist: OK -- found ${workerFile} in dist/assets/`);
