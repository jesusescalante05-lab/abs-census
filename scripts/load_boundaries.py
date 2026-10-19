"""Load ASGS STE/SA2/LGA boundaries (2016 & 2021) into geo.region."""

import argparse
import logging
import math
import sys
from pathlib import Path

import geopandas as gpd
import psycopg2
import pyproj
import shapely
from psycopg2.extras import execute_values
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from geo_code_columns import (
    BOUNDARY_AREA_COL,
    BOUNDARY_CODE_COL,
    BOUNDARY_NAME_COL,
    BOUNDARY_PARENT_GCCSA_COL,
    BOUNDARY_PARENT_SA3_COL,
    BOUNDARY_PARENT_SA4_COL,
    BOUNDARY_SOURCE,
    BOUNDARY_SRID,
    BOUNDARY_STATE_COL,
    LEVELS,
    YEARS,
)
from logging_setup import setup_logging

logger = logging.getLogger("load_boundaries")

TARGET_SRID = 7844
SAMPLE_POINT_LONLAT = (151.2093, -33.8688)  # Sydney, for datum-shift logging


def is_missing_geom(geom):
    """pyogrio/geopandas can represent a missing geometry as None or as a
    bare float NaN, depending on the source driver."""
    return geom is None or (isinstance(geom, float) and math.isnan(geom))


def repair_to_multipolygon(geom):
    """Returns (multipolygon_or_None, was_invalid, was_dropped)."""
    if is_missing_geom(geom):
        return None, False, False

    was_invalid = not geom.is_valid
    g = shapely.make_valid(geom) if was_invalid else geom

    polys = []

    def collect(part):
        if isinstance(part, Polygon):
            if not part.is_empty:
                polys.append(part)
        elif isinstance(part, MultiPolygon):
            polys.extend(p for p in part.geoms if not p.is_empty)
        elif isinstance(part, GeometryCollection):
            for sub in part.geoms:
                collect(sub)
        # Point/LineString artifacts from make_valid are silently dropped

    collect(g)

    if not polys:
        return None, was_invalid, was_invalid

    return MultiPolygon(polys), was_invalid, False


def log_datum_transform(year):
    source_epsg = BOUNDARY_SRID[year]
    if source_epsg == TARGET_SRID:
        logger.info("%s: source already EPSG:%d, no reprojection needed", year, TARGET_SRID)
        return

    transformer = pyproj.Transformer.from_crs(
        f"EPSG:{source_epsg}", f"EPSG:{TARGET_SRID}", always_xy=True
    )
    logger.info("%s: transformer = %s", year, transformer.description)

    lon, lat = SAMPLE_POINT_LONLAT
    lon2, lat2 = transformer.transform(lon, lat)
    geod = pyproj.Geod(ellps="GRS80")
    _, _, shift_m = geod.inv(lon, lat, lon2, lat2)
    logger.info("%s: sample point (Sydney) shift = %.3f m", year, shift_m)


def load_one(conn, year, level):
    src = BOUNDARY_SOURCE[(year, level)]
    logger.info("Reading %s %s from %s", year, level, src["path"])
    gdf = gpd.read_file(src["path"], layer=src["layer"])

    source_epsg = gdf.crs.to_epsg()
    if source_epsg != BOUNDARY_SRID[year]:
        logger.warning(
            "%s %s: source CRS EPSG:%s differs from expected EPSG:%s",
            year, level, source_epsg, BOUNDARY_SRID[year],
        )
    if source_epsg != TARGET_SRID:
        gdf = gdf.to_crs(epsg=TARGET_SRID)

    code_col = BOUNDARY_CODE_COL[(year, level)]
    name_col = BOUNDARY_NAME_COL[(year, level)]
    area_col = BOUNDARY_AREA_COL[(year, level)]
    state_col = BOUNDARY_STATE_COL.get((year, level))

    rows = []
    total = len(gdf)
    null_count = 0
    invalid_count = 0
    dropped_count = 0

    for _, feat in gdf.iterrows():
        geom, was_invalid, was_dropped = repair_to_multipolygon(feat.geometry)
        if is_missing_geom(feat.geometry):
            null_count += 1
        if was_invalid:
            invalid_count += 1
        if was_dropped:
            dropped_count += 1

        state_code = str(feat[state_col]) if state_col else None
        if level == "SA2":
            parent_sa3 = str(feat[BOUNDARY_PARENT_SA3_COL[year]])
            parent_sa4 = str(feat[BOUNDARY_PARENT_SA4_COL[year]])
            parent_gccsa = str(feat[BOUNDARY_PARENT_GCCSA_COL[year]])
        else:
            parent_sa3 = parent_sa4 = parent_gccsa = None

        wkb = psycopg2.Binary(shapely.to_wkb(geom)) if geom is not None else None

        rows.append((
            year,
            level,
            str(feat[code_col]),
            str(feat[name_col]),
            state_code,
            parent_sa3,
            parent_sa4,
            parent_gccsa,
            float(feat[area_col]) if feat[area_col] is not None else None,
            wkb,
        ))

    repaired_count = invalid_count - dropped_count
    logger.info(
        "%s %s: %d rows, %d null geom, %d invalid, %d repaired, %d dropped",
        year, level, total, null_count, invalid_count, repaired_count, dropped_count,
    )

    cur = conn.cursor()
    # census.value FK-references geo.region; clear dependent fact rows first so a
    # boundary refresh is never blocked by stale references (they get reloaded by
    # load_census_values.py afterward, same as a from-scratch run would do).
    cur.execute("DELETE FROM census.value WHERE census_year = %s AND geo_level = %s", (year, level))
    cur.execute("DELETE FROM geo.region WHERE census_year = %s AND geo_level = %s", (year, level))

    insert_sql = """
        INSERT INTO geo.region
            (census_year, geo_level, region_code, region_name, state_code,
             parent_sa3, parent_sa4, parent_gccsa, area_sqkm, geom)
        VALUES %s
    """
    execute_values(
        cur,
        insert_sql,
        rows,
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_GeomFromWKB(%s), 7844))",
    )
    conn.commit()

    cur.execute(
        """
        SELECT DISTINCT ST_SRID(geom) FROM geo.region
        WHERE census_year = %s AND geo_level = %s AND geom IS NOT NULL
        """,
        (year, level),
    )
    srids = {r[0] for r in cur.fetchall()}
    if srids and srids != {TARGET_SRID}:
        raise RuntimeError(f"{year} {level}: unexpected SRID(s) in geo.region: {srids}")
    logger.info("%s %s: verified ST_SRID = %s for all non-null geometries", year, level, srids or "{} (all NULL)")
    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Load ASGS boundaries into geo.region.")
    parser.add_argument("--year", type=int, choices=YEARS)
    parser.add_argument("--level", choices=LEVELS)
    args = parser.parse_args()

    years = [args.year] if args.year else list(YEARS)
    levels = [args.level] if args.level else list(LEVELS)

    conn = get_connection()
    try:
        for year in years:
            log_datum_transform(year)
        for year in years:
            for level in levels:
                load_one(conn, year, level)
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging("load_boundaries")
    main()
