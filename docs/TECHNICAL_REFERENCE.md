# ABS Census 2016 & 2021 PostGIS Pipeline — Technical Reference

This document describes the `abs-census` project as it actually exists on disk and in the database as of the last full load. Nothing here is aspirational — every number in Section 5 comes from `logs/load_20261019_1744.log` (the latest successful `load_all.py` run) or a live query against the database run immediately afterward.

## 1. Project structure

```
abs-census/
├── .env                    # your real DB credentials (gitignored, not committed)
├── .env.example            # placeholder template for .env (committed)
├── .gitignore
├── CLAUDE.md                # note that scripts must run under .venv
├── requirements.txt         # pinned Python dependencies
├── data/
│   ├── sources.csv          # manifest of every downloaded file (url, filename, date, size, sha256)
│   └── raw/                 # downloaded ABS files (gitignored, ~1.1 GB) — boundaries/ and datapacks/, by year
├── docs/
│   └── TECHNICAL_REFERENCE.md   # this file
├── logs/                    # one timestamped log per script run (gitignored)
├── sql/
│   └── 00_reset_database.sql    # drops and recreates the entire DB schema (destructive)
└── scripts/
    ├── download_abs.py          # fetches/unzips the 10 source files from abs.gov.au, writes data/sources.csv
    ├── db.py                     # get_connection() — reads PG* vars from .env via python-dotenv
    ├── logging_setup.py          # setup_logging() — stdout + logs/load_<timestamp>.log
    ├── geo_code_columns.py       # per-(year, geo_level) source paths and column-name lookup tables
    ├── load_boundaries.py        # loads ASGS STE/SA2/LGA boundaries into geo.region
    ├── load_variable_metadata.py # loads Census DataPack variable metadata into census.variable
    ├── load_datapack_stage.py    # loads each DataPack CSV as-is into stage.<table>_<geo>_<year>
    ├── load_census_values.py     # unpivots staged tables into the long/tidy census.value
    └── load_all.py               # runs all four loaders above in order
```

`.venv/` (the virtual environment) and `data/raw/` and `logs/` are gitignored and not listed above as tracked content, though they exist on disk.

## 2. Environment setup

**Requirements:** Python 3.13 (the pinned package versions in `requirements.txt` were resolved against this interpreter), and a reachable PostgreSQL 17 server with the PostGIS extension available (`CREATE EXTENSION postgis` is run by `00_reset_database.sql`).

**`requirements.txt`** (exact pinned versions):
```
requests==2.34.2
psycopg2-binary==2.9.13
geopandas==1.2.0
shapely==2.2.0
pyogrio==0.13.0
openpyxl==3.1.5
pyproj==3.8.0
python-dotenv==1.2.4
```

**`.env`** (not committed; copy from `.env.example` and fill in real values):
```
PGHOST=localhost
PGPORT=5432
PGDATABASE=abs_census
PGUSER=postgres
PGPASSWORD=changeme
```
`scripts/db.py` loads this file via `python-dotenv`'s `load_dotenv()` and reads `PGHOST`/`PGPORT`/`PGDATABASE`/`PGUSER`/`PGPASSWORD` from the process environment (so real environment variables work too, e.g. in CI, without a `.env` file at all).

### Rebuilding from scratch, step by step

1. **Clone/copy the repo**, then `cd abs-census`.
2. **Create the virtual environment:**
   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install --upgrade pip
   .venv\Scripts\python -m pip install -r requirements.txt
   ```
3. **Create `.env`:** copy `.env.example` to `.env` and fill in your real Postgres host/port/database/user/password. A database with the PostGIS extension available must already exist (e.g. `createdb abs_census`); `00_reset_database.sql` runs `CREATE EXTENSION IF NOT EXISTS postgis` but does not create the database itself.
4. **Download the source files:**
   ```
   .venv\Scripts\python scripts\download_abs.py
   ```
   This fetches all 10 files (4 boundary zips, 6 DataPack zips) into `data/raw/`, extracts them, and writes `data/sources.csv`. Safe to re-run — already-downloaded files are skipped unless `--force` is passed.
5. **Build the database schema** (connect with `psql` or any Postgres client using the same credentials as `.env`, then run):
   ```
   psql -f sql/00_reset_database.sql
   ```
   This is destructive — it drops and recreates the `analysis`, `census`, `geo`, `ref`, and `stage` schemas. Only run it against a database you intend to fully wipe and rebuild.
6. **Run the full load:**
   ```
   .venv\Scripts\python scripts\load_all.py
   ```
   This took **~1 hour 32 minutes** end-to-end on the last run (17:44:01 → 19:16:37), dominated by the `census.value` unpivot step (step 4). Progress and results are written to both stdout and a new `logs/load_<YYYYMMDD_HHMM>.log` file.
7. **Expect the database to grow to roughly 14 GB** (see Section 5 for the exact measured breakdown).

Individual loader scripts can also be run standalone with `--year`/`--level`/`--table` filters (see Section 3) for testing a subset without redoing the full load.

## 3. Scripts

### `scripts/download_abs.py`
- **Inputs:** a hardcoded `SOURCES` list of 10 `(category, year, geography, filename, url)` entries (4 ASGS boundary zips, 6 Census GCP DataPack zips, covering 2016 and 2021). CLI flags: `--only {boundaries,datapacks}`, `--year {2016,2021}`, `--force`.
- **Outputs:** each file downloaded to `data/raw/<category>/<year>/<filename>`, extracted into a sibling folder named after the zip (minus `.zip`), and one row appended to `data/sources.csv` (`url, filename, download_date, file_size_bytes, sha256`).
- **Key logic:** streams each download to a `.part` temp file (renamed to the final name only on full success) with up to 3 retries and exponential backoff; URL-encodes the 2016 ABS URLs (which contain literal spaces in their query string) via `urllib.parse.quote`; computes SHA-256 over the full downloaded file.
- **Checks:** skips re-downloading if the destination file already exists (unless `--force`); skips re-extracting if the extraction folder already exists and is non-empty; skips re-adding a manifest row if the filename is already in `data/sources.csv`.

### `scripts/db.py`
- **Inputs:** `.env` file (via `python-dotenv`) or real process environment variables `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`.
- **Outputs:** a `psycopg2` connection object from `get_connection()`.
- **Key logic:** none beyond the direct `psycopg2.connect()` call — intentionally thin, single place every other script gets a DB connection from.
- **Checks:** none; a missing env var raises `KeyError` immediately on connect.

### `scripts/logging_setup.py`
- **Inputs:** a `run_name` string (used as the logger name for the initial "Logging to ..." message).
- **Outputs:** configures the root logger with two handlers — `StreamHandler(stdout)` and `FileHandler(logs/load_<YYYYMMDD_HHMM>.log)` — and returns the log file path.
- **Key logic:** creates `logs/` if missing; timestamp is the moment `setup_logging()` is called, so each script invocation gets its own log file.
- **Checks:** none.

### `scripts/geo_code_columns.py`
Not a script with a `main()` — a pure lookup-table module imported by the loaders. Defines, for every `(year, geo_level)` pair across `YEARS = (2016, 2021)` and `LEVELS = ("STE", "SA2", "LGA")`:
- `BOUNDARY_SOURCE`: file path + GeoPackage layer name (`None` for shapefiles).
- `BOUNDARY_SRID`: `{2016: 4283, 2021: 7844}`.
- `BOUNDARY_CODE_COL` / `BOUNDARY_NAME_COL` / `BOUNDARY_STATE_COL` / `BOUNDARY_AREA_COL`: the actual column names in the boundary files (verified directly against the downloaded files via `pyogrio.read_info`, not assumed — see Section 6).
- `BOUNDARY_PARENT_SA3_COL` / `_SA4_COL` / `_GCCSA_COL`: SA2-only parent-geography columns, keyed by year only.
- `DATAPACK_CODE_COL`: the geography-code column name as it appears in the DataPack CSV (which differs from the boundary file's column name for STE and LGA — see Section 6).
- `normalize_region_code()`: strips ABS's `"LGA"` text prefix from DataPack LGA codes (defined but not actually called elsewhere — the equivalent logic is inlined as a SQL `regexp_replace` in `load_census_values.py`'s `region_code_expr()`).

### `scripts/load_boundaries.py`
- **Inputs:** the 6 boundary source files (2 GeoPackage layers × 2 years, 2 LGA shapefiles), via `geo_code_columns.BOUNDARY_SOURCE`. CLI flags: `--year`, `--level`.
- **Outputs:** rows in `geo.region` for the selected `(year, level)` combinations.
- **Key logic:**
  - `log_datum_transform(year)`: for 2016, builds `pyproj.Transformer.from_crs("EPSG:4283", "EPSG:7844", always_xy=True)`, logs `transformer.description`, and logs the shift (via `pyproj.Geod(ellps="GRS80").inv(...)`) for a fixed Sydney sample point. For 2021 (already EPSG:7844), logs that no reprojection is needed.
  - `repair_to_multipolygon(geom)`: if a geometry is invalid, runs `shapely.make_valid()`, then recursively collects only `Polygon`/`MultiPolygon` parts (discarding any point/line artifacts and descending into `GeometryCollection`s), reassembling a single `MultiPolygon`. Returns `None` if nothing polygonal survives.
  - `is_missing_geom(geom)`: treats both `None` and a bare `float('nan')` as "no geometry" — `pyogrio`/`geopandas` represent missing geometry differently depending on the source driver (confirmed the hard way — see Section 6).
  - `load_one(conn, year, level)`: reads the source via `geopandas.read_file`, reprojects to EPSG:7844 if needed, repairs/casts every geometry, builds one row per feature (mapping source columns via `geo_code_columns`), deletes existing `census.value` rows for that `(year, level)` **then** existing `geo.region` rows for that `(year, level)`, bulk-inserts via `psycopg2.extras.execute_values` with `ST_SetSRID(ST_GeomFromWKB(%s), 7844)`, then re-queries `ST_SRID` to confirm.
- **Checks:** logs a warning if the source file's actual CRS doesn't match the expected `BOUNDARY_SRID[year]`; after insert, queries `SELECT DISTINCT ST_SRID(geom) ... WHERE geom IS NOT NULL` and raises `RuntimeError` if it's anything other than `{7844}` (or empty, for an all-NULL-geometry slice); logs per-`(year, level)` counts of total rows, null-geometry rows, invalid-geometry rows, successfully-repaired rows, and dropped (un-repairable) rows.

### `scripts/load_variable_metadata.py`
- **Inputs:** the two `Metadata_<year>_GCP_DataPack*.xlsx` files (one per year, from the STE DataPack's `Metadata/` folder — the same metadata applies to all three geographies). CLI flag: `--year`.
- **Outputs:** rows in `census.variable` for the selected year(s).
- **Key logic:**
  - `parse_metadata(path)`: opens the workbook with `openpyxl` (`read_only=True`), finds the sheet whose name contains "cell descriptors" (case-insensitive — the sheet is literally named differently between years: `"Cell Descriptors Information"` in 2021 vs `"Cell descriptors information"` in 2016), then scans rows until it finds one containing both `"sequential"` and `"short"` (after lowercasing and stripping spaces) to locate the header — row numbers differ by file, so this is detected, not hardcoded. Extracts `(Sequential, DataPackfile, Short, Long)` per data row, skipping any row missing `Sequential`, `Short`, or the table-id column.
  - `check_collisions(rows, year)`: builds a `(table_id, short_code) -> variable_code` map while scanning for any case where the same `(table_id, short_code)` pair maps to two different `variable_code` values.
  - `load_one(conn, year)`: parses, checks collisions (raises `RuntimeError` if any found — would mean a DataPack CSV column can't be resolved unambiguously), deletes existing `census.variable` rows for that year, bulk-inserts the rest.
- **Checks:** the collision check above; `RuntimeError` if no header row is found at all.

### `scripts/load_datapack_stage.py`
- **Inputs:** every DataPack CSV under `data/raw/datapacks/<year>/<year>_GCP_<level>_for_AUS_short-header/<data folder>/*.csv`. CLI flags: `--year`, `--level`, `--table` (repeatable).
- **Outputs:** one Postgres table per CSV, named `stage.<table_code_lower>_<level_lower>_<year>` (e.g. `stage.g01_sa2_2021`), with the first column (geography code) as `TEXT` and every other column as `NUMERIC`, column names double-quoted to preserve ABS's exact original casing (e.g. `"Tot_P_M"`, not `tot_p_m`).
- **Key logic:**
  - `iter_datapack_csvs(year, level)`: finds the single data subfolder inside each DataPack folder (excluding `Metadata`/`Readme` — the subfolder's own name varies, e.g. `"2021 Census GCP States and Territories for AUS"` vs `"2016 Census GCP States and Territories for AUST"`), then matches each CSV filename against `FILENAME_RE` (`^\d{4}Census_([A-Za-z0-9]+)_AUST?_([A-Z0-9]+)\.csv$`) to extract the table code and geography suffix (the regex's `AUST?` handles both 2021's `AUST` and 2016's `AUS`).
  - `load_one_csv(...)`: reads just the header row to build the `CREATE TABLE` column list, `DROP TABLE IF EXISTS` + `CREATE TABLE`, then `COPY ... FROM STDIN WITH (FORMAT csv, HEADER true, NULL '..')` streaming the CSV file directly (no row-by-row Python parsing).
- **Checks:** logs a warning if a CSV's filename geography suffix doesn't match the `--level` being processed, or if a CSV's first column name doesn't match the expected `DATAPACK_CODE_COL` for that `(year, level)`; logs a warning and skips any filename that doesn't match `FILENAME_RE` at all.

### `scripts/load_census_values.py`
- **Inputs:** every table in the `stage` schema matching `stage.<table>_<level>_<year>`; `census.variable`; `geo.region`. CLI flags: `--year`, `--level`, `--table` (repeatable).
- **Outputs:** rows in `census.value`.
- **Key logic:**
  - `discover_stage_tables(...)`: lists `information_schema.tables` for schema `stage` and parses each name back into `(year, level, table_id)` via `STAGE_TABLE_RE`.
  - For each stage table: `stage_columns()` reads its columns (first = geo code, rest = data columns); `resolve_variable_codes()` looks up each data column's `short_code` against `census.variable` for that `(year, table_id)` to get the real `variable_code` (the metadata `Sequential` value), separating out any columns with no match.
  - `region_code_expr()`: builds a SQL `CASE WHEN geo_level = 'LGA' THEN regexp_replace(..., '^LGA', '') ELSE ... END` expression (via `psycopg2.sql`, not string formatting) to normalize LGA codes in-query.
  - `find_orphans()`: anti-joins the stage table's normalized region codes against `geo.region` to find any that don't exist there.
  - `insert_values()`: builds one `INSERT INTO census.value ... SELECT ... FROM (unpivot CTE) src JOIN geo.region g ON (...)` per stage table — the unpivot itself is a `CROSS JOIN LATERAL (VALUES ('var1', t."col1"), ('var2', t."col2"), ...)`, entirely server-side; the `JOIN geo.region` (not just a filter) is what silently excludes orphan codes from the insert.
  - `population_cross_check(conn, year)`: looks up the `variable_code` for `G01`/`Tot_P_P` that year, sums `census.value` by `geo_level` for `SA2` and `STE`, and logs both totals and whether they match exactly.
  - `load_all(...)`: computes the distinct `(year, level)` pairs among the selected stage tables and issues one `DELETE FROM census.value` per pair **before** the per-table loop (fixing the original delete-ordering bug — see Section 6), then processes each stage table, then runs the population cross-check once per year touched.
- **Checks:** accumulates and logs unmatched columns (short codes with no metadata match) and orphan region codes per table, then prints one final consolidated summary (counts for both); returns both lists to the caller; when run standalone (`__main__`), exits with status 1 if any orphans were found (unmatched columns alone do not trigger a non-zero exit).

### `scripts/load_all.py`
- **Inputs:** none beyond what the four loaders above need.
- **Outputs:** the fully populated database (`geo.region`, `census.variable`, `stage.*`, `census.value`).
- **Key logic:** one shared `logging_setup("load_all")` call, then runs, in order: all boundary `(year, level)` combinations → both years of variable metadata → every DataPack CSV staged → the full unpivot into `census.value`.
- **Checks:** if `load_census_values.load_all()` returns any orphans, logs an error and exits with status 1; otherwise logs a final "finished cleanly" message including the unmatched-column count.

## 4. Database schema (from `sql/00_reset_database.sql`)

Running this script **drops** (`CASCADE`) the `analysis`, `census`, `geo`, `ref`, and `stage` schemas if they exist, enables the `postgis` extension, then recreates:

### `ref.census_year`
| Column | Type | Constraint |
|---|---|---|
| `census_year` | `smallint` | **PRIMARY KEY** |
| `asgs_edition` | `text` | `NOT NULL` |
| `source_crs` | `integer` | `NOT NULL` |

Seeded with `(2016, 'ASGS 2016', 4283)` and `(2021, 'ASGS Edition 3 (2021)', 7844)`.

### `ref.geo_level`
| Column | Type | Constraint |
|---|---|---|
| `geo_level` | `text` | **PRIMARY KEY** |
| `description` | `text` | `NOT NULL` |
| `is_abs_structure` | `boolean` | `NOT NULL` |
| `sort_order` | `smallint` | `NOT NULL` |

Seeded with `('STE', ..., true, 1)`, `('LGA', ..., false, 2)`, `('SA2', ..., true, 3)`.

### `geo.region`
| Column | Type | Constraint |
|---|---|---|
| `census_year` | `smallint` | `NOT NULL`, `REFERENCES ref.census_year` |
| `geo_level` | `text` | `NOT NULL`, `REFERENCES ref.geo_level` |
| `region_code` | `text` | `NOT NULL` |
| `region_name` | `text` | `NOT NULL` |
| `state_code` | `text` | nullable (NULL for STE rows) |
| `parent_sa3` | `text` | nullable (SA2 rows only) |
| `parent_sa4` | `text` | nullable (SA2 rows only) |
| `parent_gccsa` | `text` | nullable (SA2 rows only) |
| `area_sqkm` | `double precision` | nullable |
| `geom` | `geometry(MultiPolygon, 7844)` | nullable |

**PRIMARY KEY** `(census_year, geo_level, region_code)`.
Indexes: `region_geom_gix` — GiST on `geom`; `region_year_level_idx` — btree on `(census_year, geo_level)`.

### `census.variable`
| Column | Type | Constraint |
|---|---|---|
| `census_year` | `smallint` | `NOT NULL`, `REFERENCES ref.census_year` |
| `variable_code` | `text` | `NOT NULL` |
| `table_id` | `text` | `NOT NULL` |
| `short_code` | `text` | `NOT NULL` |
| `long_descriptor` | `text` | nullable |

**PRIMARY KEY** `(census_year, variable_code)`. **UNIQUE** `(census_year, table_id, short_code)`.

### `census.value`
| Column | Type | Constraint |
|---|---|---|
| `census_year` | `smallint` | `NOT NULL` |
| `geo_level` | `text` | `NOT NULL` |
| `region_code` | `text` | `NOT NULL` |
| `variable_code` | `text` | `NOT NULL` |
| `value` | `numeric` | nullable |

**PRIMARY KEY** `(census_year, geo_level, region_code, variable_code)`.
**FOREIGN KEY** `(census_year, geo_level, region_code)` → `geo.region (census_year, geo_level, region_code)`.
**FOREIGN KEY** `(census_year, variable_code)` → `census.variable (census_year, variable_code)`.
Index: `value_year_variable_idx` — btree on `(census_year, variable_code)`.

The `stage` and `analysis` schemas are created empty — `stage` is populated dynamically at load time by `load_datapack_stage.py` (one table per DataPack CSV, not fixed DDL); `analysis` is not currently used by any script.

## 5. Load results (from `logs/load_20261019_1744.log` and live DB queries run immediately after)

**Run duration:** 17:44:01 → 19:16:37 (≈1h32m), all four steps, both years, all three geography levels.

### Boundary load (Step 1/4)

| Year | Level | Rows | Null geom | Invalid | Repaired | Dropped |
|---|---|---|---|---|---|---|
| 2016 | STE | 9 | 0 | 0 | 0 | 0 |
| 2016 | SA2 | 2,310 | 18 | 0 | 0 | 0 |
| 2016 | LGA | 563 | 18 | 0 | 0 | 0 |
| 2021 | STE | 10 | 1 | 0 | 0 | 0 |
| 2021 | SA2 | 2,473 | 19 | 0 | 0 | 0 |
| 2021 | LGA | 566 | 19 | 0 | 0 | 0 |

Zero invalid geometries in every batch — `repair_to_multipolygon`'s repair path was never actually exercised on this data; it exists for robustness, not because it was needed here.

**Datum transform** (2016 GDA94 → GDA2020 only; 2021 logged as "source already EPSG:7844, no reprojection needed"):
- Transformer selected by `pyproj`: `GDA94 to GDA2020 (1) (with axis order normalized for visualization)`
- Sample point (Sydney, 151.2093 / -33.8688) shift: **1.494 m**

Post-load SRID verification passed (`{7844}`) for all 6 batches.

### Variable metadata (Step 2/4)
- 2016: 15,535 rows parsed and inserted into `census.variable`.
- 2021: 16,984 rows parsed and inserted into `census.variable`.
- 0 `(table_id, short_code)` collisions detected in either year.

### Stage + value load (Steps 3/4 and 4/4)
- 687 stage tables created (119 tables × 3 geographies for 2021 + 110 tables × 3 geographies for 2016).
- **Population cross-check** (sum of `census.value` for `G01`'s `Tot_P_P`, SA2 total vs STE total):
  - 2016: SA2 = 23,401,897, STE = 23,401,890 (difference of 7; `match = False`)
  - 2021: SA2 = 25,422,677, STE = 25,422,797 (difference of 120; `match = False`)
  - Both mismatches are consistent with ABS's published cell-perturbation methodology for confidentiality (small random adjustments to individual cell values) — neither the log nor this document treats these as a pipeline defect.
- **Final summary line (verbatim from the log):** `0 orphan region codes across 0 (year,level) pairs; 0 unmatched DataPack columns`.
- `load_all.py` exited 0 ("Load finished cleanly").

### Final row counts (live query, immediately after the run)
```
census.value total: 96,505,134 rows
  2016 LGA:  8,746,205
  2016 SA2: 35,885,850
  2016 STE:    139,815
  2021 LGA:  9,595,960
  2021 SA2: 41,984,448
  2021 STE:    152,856
```

### Database size (live query, immediately after the run)
- Total database size: **14 GB**
- `census` schema: 12 GB (almost entirely `census.value`)
- `geo` schema: 928 MB
- `stage` schema: 490 MB
- `ref` schema: 64 kB

Note: the `geo` schema's 928 MB is larger than a single clean load would produce (a one-off measurement earlier in development, with only the 6 boundary batches loaded once, showed `geo.region` at 312 MB). `load_boundaries.py` was re-run several times against this same database during development (once to pick up a schema fix, twice more while chasing the two bugs in Section 6), and each run is a `DELETE` + `INSERT` rather than a `TRUNCATE`, leaving dead tuples that autovacuum hadn't reclaimed by the time these numbers were measured. A `VACUUM FULL geo.region` (or a fresh `00_reset_database.sql` + single `load_all.py` run) would bring it back down to roughly 300 MB. This does not affect correctness — `census.value` row counts and the orphan/population checks above are from the final, authoritative state — only disk usage.

## 6. Known issues and bugs fixed during development

1. **FK ordering on boundary reload (fixed).** `load_boundaries.py`'s `DELETE FROM geo.region WHERE census_year = %s AND geo_level = %s` failed with `psycopg2.errors.ForeignKeyViolation` the first time `load_all.py` was run against a database that already had `census.value` rows referencing those regions (left over from an earlier manual test of `load_census_values.py`). Fix: `load_one()` now deletes the matching `census.value` rows for that `(year, level)` first, before deleting `geo.region` — making a standalone re-run of `load_boundaries.py` safe at any time, not just on a fresh database.

2. **ABS's `".."` suppression marker (fixed).** The first full-pipeline run failed with `psycopg2.errors.InvalidTextRepresentation: invalid input syntax for type numeric: ".."` while staging `2016Census_G11A_AUS_STE.csv`. ABS uses the literal string `".."` (not an empty field) to mark suppressed or not-applicable cells in the short-header DataPacks. This was confirmed by scanning **all 687 DataPack CSVs** for any non-numeric, non-empty token — `".."` was the only one found, and no file had genuinely empty fields. Fix: `load_datapack_stage.py`'s `COPY` command now specifies `NULL '..'` explicitly.

3. **Missing-geometry representation is inconsistent between boundary sources.** `is_missing_geom()` exists because `2021 STE`'s GeoPackage layer returned a bare Python `float('nan')` for its one geometry-less row, whereas every other layer returned `None`. This was caught when `repair_to_multipolygon()` raised `AttributeError: 'float' object has no attribute 'is_valid'` partway through the first `load_all.py` attempt. Both representations are now handled.

4. **Boundary file vs. DataPack column-naming mismatches are real and permanent, not a bug.** For the same concept, STE's boundary-file column is `STATE_CODE_<year>` but its DataPack column is `STE_CODE_<year>`; LGA's boundary-file column is `LGA_CODE16`/`LGA_CODE21` (no underscore before the 2-digit year) but its DataPack column is `LGA_CODE_2016`/`LGA_CODE_2021` (underscore, 4-digit year). SA2 is the only level where both products agree exactly. This is why `geo_code_columns.py` keeps `BOUNDARY_CODE_COL` and `DATAPACK_CODE_COL` as two separate dictionaries rather than one — collapsing them would silently break three of the six `(year, level)` combinations.

5. **LGA region codes differ in format between products.** Boundary files store the bare code (e.g. `"10050"`); DataPack CSVs prefix it with the literal text `"LGA"` (e.g. `"LGA10050"`). `load_census_values.py` strips this prefix in-query via `regexp_replace(..., '^LGA', '')` so DataPack rows join correctly against `geo.region`.

6. **`geo` schema disk bloat from repeated development reloads** — see the note at the end of Section 5. Not a code defect; a `VACUUM FULL` or a from-scratch reload would resolve it.

7. **`census.variable` cannot be keyed on the DataPack's own `Short` column.** An explicit check of both years' full metadata found 415 (2021) and 382 (2016) `Short` values that repeat across different tables, of which 38 and 10 respectively are *genuine* semantic conflicts (the same `Short` code means different things in different tables — e.g. `P_85ov_Total` means "Persons 85+, Total" in most tables but "Age group of parent 85+, Total" in `G28`). `census.variable` is keyed on the metadata's `Sequential` column instead (confirmed 100% unique within each year), with `(census_year, table_id, short_code)` as a separate `UNIQUE` constraint used only to resolve a given DataPack CSV column to its `variable_code`.

8. **"Largest polygon part by area" is not "the mainland part" (fixed).** Both ADR-002's KNN representative-point logic and the first draft of ADR-003's display mask picked each SA2's single largest-by-area polygon part as its "main" part. For Fremantle SA2, that part is **Rottnest Island** (19.18 km²) — larger than every actual mainland piece of Fremantle (6.70 km², 3.61 km², plus two slivers). Caught by `check_display_geometry.py`'s Rottnest-exclusion check failing. Fixed by ranking parts by `(residential_mesh_block_count DESC, area_in_EPSG:7850 DESC)` instead of area alone — Rottnest is a single mesh block despite its size, while mainland Fremantle is carved into hundreds — computed once in `analysis.sa2_main_part` (Section 7) and read from there by both consumers, rather than reimplemented in Python and SQL separately.

## 7. ADR pipeline (mesh blocks, hotspot analysis, display geometry) — build order

This section covers the files added for ADR-001/002/003 (housing-stress indicator, hotspot analysis, cartographic display), which build on top of everything in Sections 1-6. Build order, after the base pipeline above has already been run once:

```
00_reset_database.sql          -- base schema (Section 4) -- destructive, not re-run for this work
01_geo_mesh_block.sql           -- geo.mesh_block table (non-destructive, CREATE ... IF NOT EXISTS)
02_fn_gi_star_confidence.sql    -- analysis.gi_star_confidence(queen_class, knn_class) function
scripts/load_mesh_blocks.py    -- loads 2021 Greater Perth mesh blocks into geo.mesh_block
10_analysis_housing_stress.sql           -- analysis.housing_stress_sa2 view (ADR-001)
11_analysis_housing_stress_hotspots.sql  -- analysis.hotspot_runs / housing_stress_hotspots tables
                                             + housing_stress_hotspots_latest view (ADR-002)
12_analysis_sa2_main_part.sql  -- analysis.sa2_main_part materialized view (single source of
                                   truth for each SA2's "main populated part" -- see issue 8 above)
scripts/hotspots_housing_stress.py  -- runs the hotspot analysis, reads sa2_main_part for KNN
                                        points, writes a new row to hotspot_runs (run_id)
13_analysis_housing_stress_display.sql  -- analysis.housing_stress_display_sa2 materialized
                                             view (ADR-003 display mask), reads sa2_main_part
```

**Mesh blocks need no separate download.** The 2021 mesh block layer (`MB_2021_AUST_GDA2020`) is already inside the Main Structure GeoPackage downloaded for SA2/STE (`data/raw/boundaries/2021/ASGS_2021_MAIN_STRUCTURE_GPKG_GDA2020/...`) — `scripts/load_mesh_blocks.py` reads it directly, filtered to `GCCSA_CODE_2021 = '5GPER'` (Greater Perth), 27,112 rows.

**`12` and `13` are coupled, deliberately without `CASCADE`.** `13` depends on `12`'s materialized view. If you change `12`'s definition, re-run `12` then `13` together — re-running `12` alone first will fail with a dependency error if `13` already exists, by design, so the coupling can't be missed silently.

**For a routine data refresh with no definition change** (reloaded mesh blocks or boundaries, but the SQL itself hasn't changed), use `scripts/refresh_display.sql` instead of re-running `12`/`13`:
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY analysis.sa2_main_part;
REFRESH MATERIALIZED VIEW CONCURRENTLY analysis.housing_stress_display_sa2;
```
`REFRESH ... CONCURRENTLY` requires a unique index on the view (both have one) and **must run outside a transaction block** (`conn.autocommit = True` when driving it from psycopg2, same as any other `CONCURRENTLY` operation) — a plain `REFRESH MATERIALIZED VIEW` works inside a transaction but locks the view against reads while it rebuilds.

**Multiple hotspot runs accumulate, by design.** `analysis.hotspot_runs`/`housing_stress_hotspots` are never wiped and replaced — each `scripts/hotspots_housing_stress.py` run adds a new `run_id`, keeping prior runs in history. `analysis.housing_stress_hotspots_latest` and `check_hotspots.py`'s expected values are pinned to whichever `run_id` is "latest" for a given `indicator`; comparing two runs directly uses `sql/diagnostics/compare_hotspot_runs.sql` (parameterised by both `run_id`s, since there's no `psql` on this machine to use its native `:variable` substitution — substitute the `{{RUN_A}}`/`{{RUN_B}}` placeholders before executing).
