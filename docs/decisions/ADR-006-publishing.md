# ADR-006: Publishing

**Product:** Perth Housing Stress Explorer
**Status:** Proposed
**Date:** 2026-11-02
**Phase:** 7 (Publish to GitHub Pages)
**Depends on:** ADR-004 (web data packaging), ADR-005 (web app)

## Context

Publishing to GitHub Pages. ADR-005 Limitation 7 set two gates before publishing: review the
`npm audit` advisories, and check the ABS attribution text.

## Publishing gate

### Gate 1: npm audit (Decision: Accepted)

- `npm audit` reports 6 moderate advisories. They are one advisory in `minimatch` (<11.0.1,
  denial of service via glob patterns), reported through 6 packages in the ESLint chain:
  `minimatch`, `@eslint/config-array`, `eslint`, `@eslint-community/eslint-utils`, `@eslint/js`,
  `eslint-plugin-react-refresh`.
- `npm audit --omit=dev` reports 0 vulnerabilities: nothing reaches the published app (`web/dist`).
- Not reachable: ESLint reads glob patterns only from the project's own config.
- Worst case: `npm run lint` slows down on the developer's machine.
- `npm audit fix --force` rejected: it would downgrade `@eslint/js` 10.0.1 to 9.39.5 (breaking).
- Review again when a new ESLint release updates `minimatch`.

### Gate 2: ABS attribution (Decision: Accepted)

- Checked on 2026-11-02 against the ABS conditions of sale (Creative Commons attribution
  section): https://www.abs.gov.au/about/legislation-and-policy/purchasing-data/abs-conditions-sale
- ABS rule: "Source: ABS" is for unchanged material; "Based on ABS data" is for modified or
  derived material, and the licence terms must be made clear.
- This product is derived (indicator, hotspots, simplified and masked boundaries), so:
  "Source:" changed to "Based on"; added "© Commonwealth of Australia" and the CC BY 4.0
  licence URL; the disclaimer now names the author's own analysis; removed the
  "(Verify this wording ...)" placeholder.
- The text is defined once, in ABS_ATTRIBUTION in scripts/export_web.py.
- check_export_web.py now checks that abs_attribution starts with "Based on", contains
  "CC BY 4.0" and the licence URL, and has no "verify this wording" placeholder.
- Re-export result: only run_metadata.json changed; both PMTiles files, sa2_points.geojson
  and sa2_details.json were byte-identical, so the export is reproducible.

## Deployment

- Host: GitHub Pages, project site https://jesusescalante05-lab.github.io/abs-census/
  (repo jesusescalante05-lab/abs-census, branch master). Pages source: "GitHub Actions".
- Node: web/.nvmrc pins 24.16.0 (same as the local machine); the workflow reads it.
- One workflow, .github/workflows/deploy.yml. Triggers: push to master, pull_request,
  workflow_dispatch.
  - Job build: npm ci, npm run lint, npm test, npm audit --omit=dev, then npm run build with
    VITE_BASE_PATH=/abs-census/, then upload web/dist as the Pages artifact.
  - Job deploy: only on master (not on pull requests); needs build; publishes the artifact.
  - Permissions: contents read, pages write, id-token write. Concurrency group "pages",
    cancel-in-progress false.
  - Every action is pinned to a full commit SHA, with its version as a comment
    (same rule as the exact npm versions in ADR-005).
- Pre-publish secrets check (2026-11-02): the full Git history contains only .env.example with
  the placeholder PGPASSWORD=changeme. The real .env is ignored by .gitignore (line 2) and was
  never committed. The commit author email is public by choice.
- Licence: a LICENSE file with the MIT licence for the code, with a note that the data in
  web/public/data/ is based on ABS data under CC BY 4.0 (see Gate 2).
- About page: no change. It is React state only and changes no URL, so a page refresh
  cannot produce a 404.
- Before pushing: run `npm run preview` (built with VITE_BASE_PATH=/abs-census/) and check
  the maplibre-gl worker request in the Network tab.
- After the first deploy: repeat the ADR-005 browser checklist on the live URL, plus:
  .pmtiles requests return HTTP 206, and the About page shows the new ABS attribution.

## Production bug: MapLibre worker 404

- **Cause.** maplibre-gl computes its worker's filename from a runtime conditional
  (`import.meta.url.endsWith('-dev.mjs') ? ... : 'maplibre-gl-worker.mjs'`), not a literal
  string. Rollup's `new URL(url, import.meta.url)` asset detection -- what makes Vite emit a
  file into dist/assets and rewrite its URL -- only fires for a literal first argument.
  Confirmed by building with VITE_BASE_PATH=/abs-census/: dist/assets contained the app's own
  JS and CSS only, no file named maplibre-gl-worker anything. The browser still requests
  /abs-census/assets/maplibre-gl-worker.mjs?v=6.14.0 at runtime and gets a 404.
- **ADR-005 bug 2 fixed dev only.** `optimizeDeps.exclude: ["maplibre-gl"]` makes Vite's dev
  server serve maplibre-gl.mjs straight from node_modules, unbundled -- so the computed
  sibling path resolves to a real file there. The production build bundles our code into one
  chunk; `import.meta.url` then points at that chunk, and the sibling file was never emitted.
- **Fix.** `MapView.jsx` imports the worker file with Vite's `?url` suffix
  (`maplibre-gl/dist/maplibre-gl-worker.mjs?url`) and calls `maplibregl.setWorkerUrl(...)`
  with the result, before any Map is created. `setWorkerUrl` is maplibre-gl's own documented
  override (`config.WORKER_URL`, checked before its broken auto-detection runs). The `?url`
  import makes Rollup emit the file for real and returns a URL already rewritten for the
  configured base, so it needs no separate BASE_URL handling (ADR-005's rule still holds, it's
  just satisfied automatically here).
- **Self-containment check.** Before relying on copying just this one file,
  node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs was checked for any static `import`,
  `new URL(..., import.meta.url)`, or dynamic `import(` of another file in the package: no
  static imports and no `new URL(...)` at all; two dynamic `import(e)` calls, both inside a
  generic "load a script from this URL" helper used for maplibre-gl's optional runtime plugin
  hooks (e.g. `setRTLTextPlugin`, external, not called anywhere in this app) -- not a
  reference to a sibling dist file. The file is self-contained for this purpose.
- **New checks.**
  1. `web/scripts/verify-dist.mjs`, run as `npm run verify:dist`: fails with a clear message
     if dist/assets has no `maplibre-gl-worker*` file after a build. Wired into
     .github/workflows/deploy.yml's build job, right after `npm run build`.
  2. The "Before pushing" step added to Deployment above: `npm run preview` against the real
     production build, checking the worker request specifically in the Network tab -- a
     file-presence check alone wouldn't catch a build that emits the file at the wrong URL.

## Limitations

- The export checks (check_export_web.py) do not run in CI, because the script connects to
  PostgreSQL first. Data files change only through the local export, which runs the full
  check (ADR-004). Planned later: an --offline mode for the file-only checks.
