# ADR-005: Web app

**Product:** Perth Housing Stress Explorer
**Status:** Accepted
**Date:** 2026-11-01
**Phase:** 6 (Web app)
**Depends on:** ADR-003 (cartography), ADR-004 (web data packaging)

## Context

ADR-004 packaged the analysis as static files with no server and no database connection. This ADR
records how those files are turned into the actual browser app: the stack, how the map is built and
made clickable, how the two map layers and their legend stay in sync with the data, how an SA2 is
found and inspected, and the accessibility and testing choices. It also records three library/build
integration bugs found while wiring the finished pieces together, and confirms none of them changed
how any value is calculated or classified.

## Decision

### Stack

A static single-page app, built by Vite and deployable as plain files (no server, consistent with
ADR-004) to a GitHub Pages project page.

| Package | Version | Role |
|---|---|---|
| `react`, `react-dom` | 19.3.1 | UI |
| `maplibre-gl` | 6.14.0 | Map rendering |
| `pmtiles` | 4.5.0 | Reads `sa2_display.pmtiles` / `sa2_outline.pmtiles` directly via HTTP range requests, no tile server |
| `vite` | 8.3.4 | Dev server and production build |
| `@vitejs/plugin-react` | 6.1.2 | React fast refresh |
| `eslint` 10.13.0, `@eslint/js` 10.0.1, `eslint-plugin-react-hooks` 7.1.1, `eslint-plugin-react-refresh` 0.5.7, `globals` 17.13.0 | — | Linting |
| `vitest` 5.0.5, `@testing-library/react` 16.3.3, `@testing-library/jest-dom` 7.0.1, `jsdom` 30.1.3 | — | Testing |

All versions are pinned exactly (no `^`/`~`) and were, at the time they were chosen, at least two
weeks old on npm — new releases are more likely to carry an unnoticed regression, and a pinned
version plus a committed `package-lock.json` (`npm ci` for installs) makes a build reproducible.

### Basemap and attribution

The basemap is OpenFreeMap's hosted Positron style (`https://tiles.openfreemap.org/styles/positron`)
— light grey, no satellite imagery, per ADR-003. MapLibre's default `AttributionControl` is left
enabled, so the basemap's own required attribution (MapLibre, OpenFreeMap, OpenMapTiles,
OpenStreetMap) renders automatically in the map's bottom-right corner. This is a **separate**
attribution from the ABS data attribution in `run_metadata.json`, which is shown on the About page —
the two credit different things (the map tiles vs. the Census data) and neither substitutes for the
other.

### One-config rule

`src/config/mapStyle.js` is the single source of truth for every colour, class label, and style
constant (ADR-002/003's confidence classes and ADR-003/004's quintile colours and outline style). No
component defines a colour or label of its own: `MapView` builds its paint expressions from it,
`Legend` builds its swatches from the same arrays via `buildQuintileLegendEntries(breaks)`, and
`SidePanel` looks up a confidence label from the same `GI_STAR_CONFIDENCE_CLASSES` array. The map and
the legend therefore cannot drift apart into two hand-maintained lists.

### Invisible click layer

The visible choropleth (`sa2-display-fill`) has real gaps — ADR-003's residential mask leaves
non-residential land unfilled — so using it to detect clicks would miss clicks there. A second,
invisible layer (`sa2-outline-fill-hit`, `fill-opacity: 0`) is drawn from `sa2_outline.pmtiles`,
which covers each SA2's full boundary, and is what click and hover handlers actually attach to.

### `BASE_URL` rule

Every data and tile URL (`sa2_display.pmtiles`, `sa2_outline.pmtiles`, `sa2_points.geojson`,
`sa2_details.json`, `run_metadata.json`) is built by `dataUrl()` in `useSa2Data.js` from
`import.meta.env.BASE_URL`, never a hardcoded `/data/...` path. `vite.config.js` sets `base` from a
`VITE_BASE_PATH` build-time environment variable, defaulting to `/` for local dev. This is the only
change needed to deploy under a GitHub Pages project sub-path (e.g. `/abs-census/`) — nothing else in
the app refers to an absolute path.

### Quintile legend from the breaks

The quintile legend's five labelled ranges are not typed by hand: `Legend` calls
`buildQuintileLegendEntries(metadata.rent_burden_quintile_breaks)`, reading the breaks from
`run_metadata.json` at runtime. If a future export run changes the breaks (ADR-004), the legend
updates automatically. The side panel's "quintile X" wording for the spatial-outlier note (below)
uses the same breaks via `quintileForValue()`, which only looks up which already-decided bracket a
given SA2's value falls into — it does not recompute the breaks themselves (ADR-004 rejected
computing quintiles in the browser).

### Legend shows only the confidence classes present in this run

`GI_STAR_CONFIDENCE_CLASSES` in `mapStyle.js` keeps all seven classes from ADR-002/003, including
`conflicting`, because that is the map's full paint expression (a future run could produce a
conflicting SA2) and the canonical colour/label list. The *legend*, however, is filtered at render
time to the classes that actually occur in the loaded `sa2_details.json` (`App.jsx` computes a
`presentConfidenceClasses` set from `detailsByCode`, passed to `Legend`). In run 2, `conflicting` has
zero SA2s (ADR-002), so it is correctly absent from the legend — listing a class nothing on the map
uses would suggest a result that isn't there. The quintile legend is not filtered this way: its five
bands come directly from `run_metadata.json`'s breaks (ADR-004), not from a presence check, and by
construction every valid SA2 falls into exactly one of them.

### Labels from points

The map's labels are a MapLibre symbol layer sourced from `sa2_points.geojson`, filtered to
`robust_hotspot` / `robust_coldspot` only (ADR-002/003), using the OpenFreeMap Positron style's own
font stack (`Noto Sans Bold`) rather than shipping separate font glyphs. `text-allow-overlap` and
`text-ignore-placement` are both set `false` explicitly, not left to MapLibre's (already-`false`)
default, so this stays documented, collision-aware behaviour rather than an implicit default someone
could change later: a robust hotspot/coldspot label that would collide with another placed label —
including the basemap's own place names, like "Mandurah" — is dropped, never forced on top of one. A
white text halo (`text-halo-color: #ffffff`, `text-halo-width: 1.5`) keeps a label legible against the
choropleth fill without needing heavy contrast that would itself compete with basemap labels.

### SA2 search, selection and the side panel

- **Selector:** `SidePanel` has a native `<select>` (not a custom combobox) listing all 185 SA2
  names, sorted alphabetically, sourced from `sa2_points.geojson` via `useSa2Data`'s `regions`. A
  native element was chosen over a styled widget so keyboard operation, screen-reader labelling, and
  type-ahead all come from the browser for free (plan Section 6).
- **One selection path:** both the map click handler and the selector call the same
  `App.jsx` function, `selectRegion(code)`, which sets `selectedRegionCode` and flies the map to the
  region's point coordinates. Picking an SA2 by name always does the same thing as clicking it.
- **Status-aware values:** the side panel never shows a NULL burden as a blank or a zero. When
  `rent_status` / `mortgage_status` isn't `"ok"` (ADR-001 R6), it shows the specific reason instead
  (e.g. "Too few households with a mortgage in this SA2 for a reliable median repayment.").
- **Distribution strip:** below the detail fields, a small horizontal strip shows where this SA2's
  `rent_burden` ranks among Perth's 165 valid SA2s, with a dot at its own value. The five quintile
  bands are drawn as **five equal-width segments**, not to a 0-based value scale, and the dot is
  placed *within its own band* by how far the value falls between that band's own lower and upper
  edge. A value-based scale was tried first and rejected: because quintile breaks are not evenly
  spaced (e.g. class 1 spans 0 to ~0.17, more than half of the 0–0.30 range, for the same 20% of SA2s
  as every other class), it made the lowest class look like it covers most of Perth. Equal-width bands
  show the one fact the strip is meant to show — relative rank — correctly; the exact value is still
  available via the dot's tooltip and the "Rent burden" field above. The strip uses the same
  `RENT_BURDEN_QUINTILE_COLORS` and `rent_burden_quintile_breaks` as the quintile map and its legend —
  one more place the one-config rule applies. Shown only when `rent_status === "ok"` (no strip for a
  NULL burden).
- **Spatial-outlier note:** when `local_moran_class === "spatial_outlier"` (ADR-002), the panel adds
  a plain-language sentence: *"This SA2's own burden is in quintile X, but it sits inside an area
  that's mostly high/low-burden."* The neighbourhood direction comes from the second letter of
  `local_moran_quadrant` (`H`/`L`); the SA2's own quintile from `quintileForValue`.
- **Limitation line:** every SA2 with a detail shown also shows "Area-level estimate; likely
  understates renters' burden." (ADR-001 limitation 1), so the headline caveat is visible wherever a
  number is.

### Accessibility choices

- `LayerSwitch` is a native `<fieldset>`/`<legend>` radiogroup, not a styled toggle — arrow-key and
  screen-reader behaviour come from the browser.
- The SA2 selector is a native `<select>` (see above), with a `<label htmlFor>` association rather
  than a placeholder-only hint.
- `AboutPage` is marked `role="dialog" aria-modal="true" aria-labelledby="about-heading"`, and its
  close control is a real `<button>` with `aria-label="Close"` (its visible content is just "×").

### Tests

`src/app.test.jsx` (Vitest + Testing Library, `jsdom` environment, 17 cases) covers:

- `mapStyle.js`: the confidence and quintile MapLibre `match` expressions have one branch per class
  plus a fallback; `buildQuintileLegendEntries` and `quintileForValue` against the project's real,
  committed `run_metadata.json` breaks.
- `dataUrl()` builds from `BASE_URL`, not a hardcoded root.
- `LayerSwitch`, `Legend` (both layers, including the quintile note only appearing for the quintile
  layer, and that a class with zero SA2s in this run is filtered out of the confidence legend),
  `SidePanel` (the selector, the no-selection hint, a NULL-burden status note, the distribution strip
  appearing with the right value and disappearing when the burden is NULL, and — using the two real
  cases from ADR-002 finding 2 — the spatial-outlier note for both Mandurah – North and Claremont, and
  its absence for an ordinary not-significant SA2), and `ZoomToClusterButton`.

`MapView.jsx` itself is **not** unit-tested: it drives real WebGL canvas rendering, which `jsdom`
does not implement, so a unit test could only mock MapLibre away and would not catch a real rendering
problem (as the three bugs below show). It was instead verified by running the dev server and
checking it in a real browser against the known ADR-002 run 2 results (see Validation).

### Integration bugs found and fixed

All three were found by actually loading the finished app in a browser, not by the test suite (which
is why `MapView.jsx` is smoke-tested manually, above). Each is a library/build-tool plumbing problem,
not a data or definitional change, so none required the "stop before fixes that change a definition"
gate in this file — confirmed below for each.

1. **`maplibre-gl` has no default export.** `import maplibregl from "maplibre-gl"` failed at runtime
   with `SyntaxError: ... does not provide an export named 'default'`. `maplibre-gl@6.14.0`'s ESM
   build (`dist/maplibre-gl.mjs`) exports only named bindings (`Map`, `addProtocol`, etc.). **Fix:**
   a namespace import (`import * as maplibregl from "maplibre-gl"`) in `MapView.jsx`, so every
   existing `maplibregl.Map` / `maplibregl.addProtocol` call keeps working unchanged. *Does not
   affect any calculated value or classification* — it only changes how one module is loaded.

2. **Vite's dependency pre-bundler can't resolve maplibre's worker.** The map basemap and SA2 layers
   never rendered; the console showed `Worker failed to load`, and the worker's pre-bundled chunk
   (`maplibre-gl-worker.mjs`) 504'd. MapLibre loads its tile-processing worker via a dynamic
   `new Worker(new URL(..., import.meta.url))`, which esbuild's dependency pre-bundling (used by
   Vite's dev server) does not resolve correctly. **Fix:** `optimizeDeps: { exclude: ["maplibre-gl"] }`
   in `vite.config.js`, so Vite serves it as native ESM from `node_modules` instead, which resolves
   the worker's URL correctly. *Does not affect any calculated value or classification* — it only
   changes which tool serves one dependency's source during development.

3. **`map.addImage()` rejects a raw `HTMLCanvasElement`.** The not-analysed hatch pattern
   (ADR-003/004) threw `RangeError: mismatched image size. expected: 0 but got: 256` on first paint.
   MapLibre's `addImage()` only accepts an `HTMLImageElement`, `ImageBitmap`, `ImageData`, or a plain
   `{width, height, data}` object — a bare canvas falls through to the `{width, height, data}` branch
   with no `data` property, producing a zero-length array. **Fix:** the hatch helper
   (`createHatchImageData` in `MapView.jsx`) now returns `ctx.getImageData(0, 0, size, size)` instead
   of the canvas element itself. *Does not affect any calculated value or classification* — the
   hatch's colour and which SA2s receive it (`display_type = 'full_extent'`, ADR-003) are unchanged;
   this only changes how the hatch's pixels are packaged for MapLibre's texture upload.

## Results

- `npm test`: 17/17 pass (`vitest run`).
- `npm run lint`: clean (`eslint .`, flat config added — `package.json`'s `lint` script existed
  before a config file did).
- `npm run build`: production build succeeds (single JS bundle, ~1.28 MB / 358 kB gzipped — expected
  for a MapLibre-based app; not code-split, see Limitations).
- Manual browser verification against the ADR-002 run 2 results: the confidence map shows Claremont
  (WA) as the one robust coldspot (dark blue, labelled) and all five robust hotspots — Mandurah,
  Mandurah – North, Mandurah – South, Mandurah – East and Greenfields — as the robust hotspot cluster
  (dark red); the quintile map shows Claremont in the
  highest (darkest) class, consistent with its `rent_burden` of 0.222; the side panel's
  spatial-outlier note correctly reproduces ADR-002 finding 2 for both Mandurah – North ("quintile 3
  ... mostly high-burden") and Claremont ("quintile 5 ... mostly low-burden"); Osborne Park
  Industrial (`mortgage_status = 'few_mortgaged'`) shows the status explanation instead of a number;
  "Zoom to robust hotspot cluster" flies to exactly the Mandurah–Peel SA2s; the About page's figures
  match `run_metadata.json` exactly; the distribution strip's dot lands in the correct band and
  disappears for a not-analysed SA2 (Kings Park); the confidence legend lists 6 classes, not 7
  (`conflicting` absent); and the zoom-to-cluster button and side panel no longer overlap.

## Alternatives considered

| Option | Decision | Reason |
|---|---|---|
| A styled autocomplete/combobox for the SA2 selector | Rejected | A native `<select>` gives keyboard and screen-reader support for free at 185 items; no custom widget to maintain |
| A separate fetch/hook just for the selector's SA2 list | Rejected | `useSa2Data` already loads once on mount; added `sa2_points.geojson` to the same `Promise.all` instead of a second data-loading path |
| Recomputing quintile breaks in the browser | Rejected | Already rejected in ADR-004; only a bracket *lookup* against the committed breaks is done client-side, for side-panel wording, not a recomputation |
| Leave `maplibre-gl` in Vite's default dependency pre-bundling | Rejected (after bug 2) | Its worker chunk reliably 504'd; excluding it from pre-bundling is the documented workaround |
| Ship a static hatch pattern image asset | Rejected | Generating it on a `<canvas>` at runtime needs no extra asset and always matches the configured hatch colour |
| `react-map-gl` or another React wrapper around MapLibre | Rejected | The app's MapLibre usage (imperative source/layer setup, event handlers) is simple enough that the wrapper would add a dependency without reducing code |

## Limitations

1. `MapView.jsx` (the actual map rendering) has no automated test — `jsdom` has no WebGL, so a unit
   test could only mock MapLibre away. It relies on the manual browser verification in Results, which
   is not re-run automatically on every change.
2. No visual regression testing (e.g. screenshot diffing) — a future change to `mapStyle.js` or the
   layer definitions could silently change the rendered map without failing any test.
3. No CI pipeline runs `npm test` / `npm run lint` / `npm run build` yet; they were run locally for
   this ADR.
4. The basemap is a live third-party dependency (OpenFreeMap); the app has no offline fallback if
   that service is unavailable.
5. `npm audit` reports 6 moderate-severity advisories, all in transitive dependencies (nothing in
   `package.json`'s direct dependency list); not reviewed as part of this ADR.
6. No GitHub Pages deploy workflow exists yet. `VITE_BASE_PATH` is wired so a build can be deployed
   to a project sub-path, but nothing builds or publishes `web/dist` automatically.
7. **Before publishing (Phase 7):** the 6 `npm audit` advisories (Limitation 5) must be reviewed, and
   `run_metadata.json`'s `abs_attribution` text must be checked against the ABS's current attribution
   guidance (ADR-004 already flags the text itself; this repeats it as a publishing gate, not just a
   data-export note).

## Validation

- `npm test`, `npm run lint`, `npm run build` all pass (see Results).
- Browser smoke test checklist (see Results) covers: basemap + both choropleth layers render; labels
  appear only for robust hotspot/coldspot SA2s; map click and the SA2 selector both select the same
  SA2 and fly to it; a NULL burden shows its status reason, never a blank or zero; the spatial-outlier
  note matches ADR-002 finding 2 for both of its real cases; the zoom-to-cluster button's bounding box
  matches `run_metadata.json`; the About page's statistics match `run_metadata.json` exactly.
- The unit tests exercise component logic, not map rendering, so they cannot verify a rendering fix;
  the manual browser test does. The code changes for the three integration bugs touch only module
  loading, dependency serving, and how one image's pixels are packaged. No rendered colour, label,
  class boundary, or side-panel or About-page value depends on those, and none of the unit tests
  needed to change for the fixes.
