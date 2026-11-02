"""Phase 5: export the housing-stress analysis for the static web map.

Writes to web/public/data/:
  sa2_display.pmtiles  -- choropleth fill geometry + attributes (gi_star_confidence,
                           rent_burden, rent_burden_quintile)
  sa2_outline.pmtiles  -- SA2 boundary outlines, topology-preserving simplified
                           (ST_CoverageSimplify) so neighbours stay edge-matched
  sa2_points.geojson   -- one representative point per SA2 (185), EPSG:4326
  sa2_details.json     -- full per-SA2 detail for the side panel (185 records)
  run_metadata.json    -- run info, global Moran's I, quintile breaks, robust-hotspot
                           bounding box, ABS attribution
"""

import json
import logging
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from logging_setup import setup_logging

logger = logging.getLogger("export_web")

OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "public" / "data"
METRIC_CRS = 7850
WGS84 = 4326
SIMPLIFY_TOLERANCE_M = 5
TILE_MINZOOM = 8
TILE_MAXZOOM = 14

# NTILE(5) splits rows by ORDER, not by value: two SA2s with the identical
# displayed (rounded) rent_burden could land in different quintiles purely
# by row order among ties. Group by the rounded value FIRST, then assign
# whole groups to quintiles by cumulative row count -- every SA2 sharing a
# displayed rent_burden always gets the same class, by construction.
QUINTILE_CTE = """
    valid AS (
        SELECT region_code, ROUND(rent_burden::numeric, 3) AS rb
        FROM analysis.housing_stress_sa2 WHERE rent_status = 'ok'
    ),
    grouped AS (
        SELECT rb, COUNT(*) AS n FROM valid GROUP BY rb
    ),
    cum AS (
        SELECT rb, SUM(n) OVER (ORDER BY rb) AS cum_n, SUM(n) OVER () AS total_n FROM grouped
    ),
    quintiles AS (
        SELECT v.region_code, v.rb,
               LEAST(5, CEIL(c.cum_n * 5.0 / c.total_n)::int) AS quintile
        FROM valid v JOIN cum c ON c.rb = v.rb
    )
"""

ABS_ATTRIBUTION = (
    "Based on Australian Bureau of Statistics (ABS) data: Census of Population and "
    "Housing, 2021, and the Australian Statistical Geography Standard (ASGS) Edition 3. "
    "© Commonwealth of Australia. "
    "Licensed under Creative Commons Attribution 4.0 International (CC BY 4.0): "
    "https://creativecommons.org/licenses/by/4.0/. "
    "The rent-burden indicator, hotspot results and display boundaries are the author's "
    "own analysis, and are not published, endorsed, or verified by the ABS."
)


def dump_json_strict(obj, path):
    """allow_nan=False: raise immediately if a NaN/Infinity ever sneaks into
    the data, rather than silently writing the invalid-per-spec `NaN` token."""
    text = json.dumps(obj, allow_nan=False, indent=2)
    path.write_text(text, encoding="utf-8")
    logger.info("Wrote %s (%d bytes)", path.name, path.stat().st_size)


def fetch_quintile_breaks(conn):
    cur = conn.cursor()
    cur.execute(
        f"""
        WITH {QUINTILE_CTE}
        SELECT quintile, MAX(rb) FROM quintiles GROUP BY quintile ORDER BY quintile;
        """
    )
    breaks = [float(row[1]) for row in cur.fetchall()]
    cur.close()
    if len(breaks) != 5:
        raise RuntimeError(f"expected 5 quintile breaks, got {len(breaks)}")
    if breaks != sorted(breaks):
        raise RuntimeError(f"quintile breaks not increasing: {breaks}")
    logger.info("rent_burden quintile breaks: %s", breaks)
    return breaks


def fetch_robust_hotspot_bbox(conn):
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT ST_XMin(bbox), ST_YMin(bbox), ST_XMax(bbox), ST_YMax(bbox)
        FROM (
            SELECT ST_Envelope(ST_Transform(ST_Collect(g.geom), {WGS84})) AS bbox
            FROM geo.region g
            JOIN analysis.housing_stress_hotspots_latest h ON h.region_code = g.region_code
            WHERE g.census_year = 2021 AND g.geo_level = 'SA2'
              AND h.gi_star_confidence = 'robust_hotspot'
        ) sub;
        """
    )
    row = cur.fetchone()
    cur.close()
    if row is None or any(v is None for v in row):
        raise RuntimeError("could not compute robust_hotspot bounding box")
    bbox = [float(v) for v in row]
    logger.info("robust_hotspot bounding box (EPSG:4326): %s", bbox)
    return bbox


def export_display_tiles(conn):
    sql = f"""
        WITH {QUINTILE_CTE}
        SELECT
            d.region_code,
            s.region_name,
            d.display_type,
            h.gi_star_confidence,
            ROUND(s.rent_burden::numeric, 3) AS rent_burden,
            q.quintile AS rent_burden_quintile,
            ST_Transform(
                ST_SimplifyPreserveTopology(ST_Transform(d.display_geom, {METRIC_CRS}), {SIMPLIFY_TOLERANCE_M}),
                {WGS84}
            ) AS geom
        FROM analysis.housing_stress_display_sa2 d
        JOIN analysis.housing_stress_sa2 s ON s.region_code = d.region_code
        LEFT JOIN analysis.housing_stress_hotspots_latest h ON h.region_code = d.region_code
        LEFT JOIN quintiles q ON q.region_code = d.region_code
    """
    gdf = gpd.read_postgis(sql, conn, geom_col="geom")
    out_path = OUT_DIR / "sa2_display.pmtiles"
    out_path.unlink(missing_ok=True)
    gdf.to_file(out_path, driver="PMTiles", layer="sa2_display", MINZOOM=TILE_MINZOOM, MAXZOOM=TILE_MAXZOOM)
    logger.info("sa2_display.pmtiles: %d features, %d bytes", len(gdf), out_path.stat().st_size)
    return len(gdf)


def export_outline_tiles(conn):
    sql = f"""
        SELECT
            g.region_code,
            g.region_name,
            ST_Transform(
                ST_SetSRID(ST_CoverageSimplify(ST_Transform(g.geom, {METRIC_CRS}), {SIMPLIFY_TOLERANCE_M}) OVER (), {METRIC_CRS}),
                {WGS84}
            ) AS geom
        FROM geo.region g
        WHERE g.census_year = 2021 AND g.geo_level = 'SA2' AND g.parent_gccsa = '5GPER'
    """
    gdf = gpd.read_postgis(sql, conn, geom_col="geom")
    out_path = OUT_DIR / "sa2_outline.pmtiles"
    out_path.unlink(missing_ok=True)
    gdf.to_file(out_path, driver="PMTiles", layer="sa2_outline", MINZOOM=TILE_MINZOOM, MAXZOOM=TILE_MAXZOOM)
    logger.info("sa2_outline.pmtiles: %d features, %d bytes", len(gdf), out_path.stat().st_size)
    return len(gdf)


def export_points(conn):
    sql = f"""
        SELECT region_code, region_name, gi_star_confidence,
               ST_Transform(point_{METRIC_CRS}, {WGS84}) AS geom
        FROM (
            SELECT s.region_code, s.region_name, h.gi_star_confidence,
                   COALESCE(
                       mp.representative_point_{METRIC_CRS},
                       ST_Transform(ST_PointOnSurface(g.geom), {METRIC_CRS})
                   ) AS point_{METRIC_CRS}
            FROM analysis.housing_stress_sa2 s
            JOIN geo.region g ON g.census_year = 2021 AND g.geo_level = 'SA2' AND g.region_code = s.region_code
            LEFT JOIN analysis.sa2_main_part mp ON mp.region_code = s.region_code
            LEFT JOIN analysis.housing_stress_hotspots_latest h ON h.region_code = s.region_code
        ) sub
    """
    gdf = gpd.read_postgis(sql, conn, geom_col="geom")
    out_path = OUT_DIR / "sa2_points.geojson"
    out_path.unlink(missing_ok=True)
    # Write as plain GeoJSON text ourselves (not gdf.to_file) so we control
    # allow_nan=False directly, rather than trusting GDAL's own JSON writer.
    records = []
    for _, row in gdf.iterrows():
        records.append({
            "type": "Feature",
            "properties": {
                "region_code": row["region_code"],
                "region_name": row["region_name"],
                "gi_star_confidence": row["gi_star_confidence"],
            },
            "geometry": {"type": "Point", "coordinates": [row["geom"].x, row["geom"].y]},
        })
    dump_json_strict({"type": "FeatureCollection", "features": records}, out_path)
    return len(gdf)


def export_sa2_details(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            s.region_code, s.region_name, s.households, s.renting, s.mortgaged,
            s.rent_status, s.mortgage_status, s.rent_burden, s.mortgage_burden,
            s.renter_share, s.social_housing_share,
            h.gi_star_confidence, h.gi_star_z, h.gi_star_p_sim,
            h.local_moran_quadrant, h.local_moran_class
        FROM analysis.housing_stress_sa2 s
        LEFT JOIN analysis.housing_stress_hotspots_latest h ON h.region_code = s.region_code
        ORDER BY s.region_code;
        """
    )
    cols = [d[0] for d in cur.description]
    records = []
    for row in cur.fetchall():
        rec = {}
        for col, val in zip(cols, row):
            if val is None:
                rec[col] = None
            elif isinstance(val, (int, str, bool)):
                rec[col] = val
            else:
                rec[col] = float(val)
        records.append(rec)
    cur.close()
    out_path = OUT_DIR / "sa2_details.json"
    dump_json_strict(records, out_path)
    return len(records)


def export_run_metadata(conn, quintile_breaks, robust_hotspot_bbox):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT run_id, code_commit, run_at, seed, permutations,
               libpysal_version, esda_version,
               global_moran_i, global_moran_z_sim, global_moran_p_sim
        FROM analysis.hotspot_runs
        WHERE indicator = 'rent_burden'
        ORDER BY run_id DESC LIMIT 1;
        """
    )
    row = cur.fetchone()
    cur.close()
    if row is None:
        raise RuntimeError("no hotspot_runs row found for indicator='rent_burden'")
    (run_id, code_commit, run_at, seed, permutations,
     libpysal_version, esda_version, moran_i, moran_z, moran_p) = row

    metadata = {
        "run_id": run_id,
        "code_commit": code_commit,
        "run_at": run_at.isoformat(),
        "seed": seed,
        "permutations": permutations,
        "libpysal_version": libpysal_version,
        "esda_version": esda_version,
        "global_moran_i": float(moran_i),
        "global_moran_z_sim": float(moran_z),
        "global_moran_p_sim": float(moran_p),
        "rent_burden_quintile_breaks": quintile_breaks,
        "robust_hotspot_bbox_4326": robust_hotspot_bbox,
        "abs_attribution": ABS_ATTRIBUTION,
    }
    out_path = OUT_DIR / "run_metadata.json"
    dump_json_strict(metadata, out_path)
    return metadata


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()

    quintile_breaks = fetch_quintile_breaks(conn)
    robust_hotspot_bbox = fetch_robust_hotspot_bbox(conn)

    n_display = export_display_tiles(conn)
    n_outline = export_outline_tiles(conn)
    n_points = export_points(conn)
    n_details = export_sa2_details(conn)
    metadata = export_run_metadata(conn, quintile_breaks, robust_hotspot_bbox)

    conn.close()

    logger.info(
        "Done: sa2_display=%d sa2_outline=%d sa2_points=%d sa2_details=%d run_id=%s",
        n_display, n_outline, n_points, n_details, metadata["run_id"],
    )


if __name__ == "__main__":
    setup_logging("export_web")
    main()
