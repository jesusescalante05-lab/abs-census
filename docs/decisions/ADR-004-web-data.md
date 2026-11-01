# ADR-004: Web data packaging

**Product:** Perth Housing Stress Explorer
**Status:** Accepted
**Date:** 2026-11-05
**Phase:** 5 (Package for web)
**Depends on:** ADR-001 (indicator), ADR-002 (hotspots, run 2), ADR-003 (cartography)

## Context

The web map must run as static files, with no server and no database connection. This ADR records
how the PostGIS results are exported for the browser: formats, geometry processing, what goes into
tiles versus JSON, and how the exported files are versioned.

## Decision

### Outputs (`web/public/data/`)

| File | Contents | Used for |
|---|---|---|
| `sa2_display.pmtiles` | Display shapes (ADR-003) with `region_code`, `region_name`, `display_type`, `gi_star_confidence`, `rent_burden` (3 dp), `rent_burden_quintile` | Map fills |
| `sa2_outline.pmtiles` | 185 SA2 boundaries with `region_code`, `region_name` | Map outlines |
| `sa2_points.geojson` | 185 points (EPSG:4326): main populated part representative point for analysed SA2s, point on surface for not-analysed SA2s; `region_code`, `region_name`, `gi_star_confidence` | Labels; future search |
| `sa2_details.json` | One record per SA2 with all side-panel fields (counts, burdens, statuses, hotspot results, local Moran quadrant) | Side panel and charts |
| `run_metadata.json` | Run id, commit, run time, seed, permutations, library versions, global Moran's I, quintile breaks, robust-hotspot bounding box, ABS attribution | About page, legend, zoom-to-cluster |

Tiles carry only what the map styles or labels. Everything else lives in JSON, loaded once.

### Vector tiles

- **Format: PMTiles**, written by the GDAL 3.12 PMTiles driver bundled with `pyogrio`. No other tool
  is required.
- **Two files, not one.** GDAL's simple write interface cannot add a second layer to an existing
  PMTiles file (tested). Two sources are equivalent for MapLibre, and the layers change at different
  rates (outlines with ABS boundaries; display with each analysis run).
- **CRS: EPSG:3857**, fixed by the format and expected by web map libraries.
- **Zoom 8–14.** Tile extent 4096 (GDAL default): about 0.6 m precision at zoom 14.

### Simplification

- **Tolerance: 5 m** (in EPSG:7850), about half a pixel at zoom 14.
- Outlines: `ST_CoverageSimplify`, which keeps shared SA2 edges aligned (no gaps or overlaps).
- Display masks: `ST_SimplifyPreserveTopology` per feature (they are not a gap-free coverage).
- The same tolerance on both layers keeps masks and outlines visually aligned at all zoom levels.

### Classes and bounds computed at export, not in the browser

- **Quintile classes** of `rent_burden` over the 165 valid SA2s, computed with Postgres
  `NTILE(5) OVER (ORDER BY rent_burden)`: five equal-count groups of 33 SA2s. The stored break for
  each class is the **maximum** `rent_burden` in that group, so class *k* covers values above break
  *k − 1* up to and including break *k*. The same `NTILE` call assigns `rent_burden_quintile` in the
  tiles, so classes and breaks are consistent by construction. These are the authoritative breaks;
  other tools (for example QGIS) use different quantile methods and can give slightly different values.
- **Robust-hotspot bounding box** (EPSG:4326) for the zoom-to-cluster control.

### JSON

- NULL values are written as `null`; NaN and Infinity are never written (`allow_nan=False`).

### Versioning of exported files

- The exported files **are committed** to Git. Automated publishing cannot reach the local database,
  so it cannot regenerate them.
- Rule: **export → run `check_export_web.py` → commit the data files together**, in the same commit.
- `run_metadata.json` records the run id and code commit, so every published file traces back to the
  analysis that produced it.

### Attribution

- The ABS attribution text in `run_metadata.json` must be checked against the ABS's current
  attribution guidance before publication.

## Results (export of run 2)

| File | Size (bytes) |
|---|---|
| `sa2_display.pmtiles` | 1,179,382 |
| `sa2_outline.pmtiles` | 883,938 |
| `sa2_points.geojson` | 66,479 |
| `sa2_details.json` | 109,103 |
| `run_metadata.json` | 1,066 |

- 185 distinct SA2s in every spatial output and in `sa2_details.json`.
- Quintile breaks (upper bound per class): 0.174, 0.187, 0.199, 0.216, 0.300.
- Robust-hotspot bounding box: 115.711, −32.615, 115.815, −32.453 (Mandurah–Peel).

## Alternatives considered

| Option | Decision | Reason |
|---|---|---|
| Single simplified GeoJSON | Rejected | Workable at 185 SA2s, but loads everything at once and does not scale to SA1s or other cities |
| Tippecanoe (via WSL or Docker) | Not needed | Neither is installed; the bundled GDAL driver works |
| One PMTiles file via separate GDAL Python bindings | Rejected | Adds a dependency that may lack the PMTiles driver; no user benefit |
| 25 m simplification | Rejected | 2–3 pixels at zoom 14; misaligns masks and outlines; saves only about 0.4 MB |
| Quintiles computed in the browser | Rejected | Class breaks would depend on client code and could not be tested |
| Labels placed on polygons | Rejected | Labels repeat across tiles; a point layer places each label once |
| Regenerate data in CI | Not possible | CI has no access to the local database |

## Validation (`scripts/check_export_web.py`)

- 185 distinct `region_code` values in each PMTiles file (read back from the tile pyramid).
- 185 features in `sa2_points.geojson`; 185 records in `sa2_details.json`, each `region_code` once.
- `gi_star_confidence` counts match run 2 (imported from `check_hotspots.py`, not retyped).
- Both JSON files parse with a strict parser that rejects NaN and Infinity.
- Five increasing quintile breaks; a bounding box inside Greater Perth.
- `run_metadata.json` run id and commit match `analysis.hotspot_runs`.
- No `rent_burden` value appears in more than one quintile (NTILE ties do not cross a class boundary).
