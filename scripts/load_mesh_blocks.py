"""Load 2021 ABS Mesh Block boundaries (Greater Perth only) into geo.mesh_block.

Reuses the Main Structure GeoPackage already downloaded for SA2/STE -- the
MB_2021_AUST_GDA2020 layer inside it is the same data as ABS's standalone
Mesh Block shapefile, so no separate download is needed.
"""

import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg2
import shapely
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from load_boundaries import is_missing_geom, repair_to_multipolygon
from logging_setup import setup_logging

logger = logging.getLogger("load_mesh_blocks")

CENSUS_YEAR = 2021
SOURCE_PATH = "data/raw/boundaries/2021/ASGS_2021_MAIN_STRUCTURE_GPKG_GDA2020/ASGS_2021_Main_Structure_GDA2020.gpkg"
SOURCE_LAYER = "MB_2021_AUST_GDA2020"
TARGET_SRID = 7844
GCCSA_FILTER = "GCCSA_CODE_2021 = '5GPER'"  # Greater Perth


def main():
    logger.info("Filtering mesh blocks to Greater Perth: %s", GCCSA_FILTER)
    gdf = gpd.read_file(SOURCE_PATH, layer=SOURCE_LAYER, where=GCCSA_FILTER)
    logger.info("Loaded %d mesh blocks from %s (layer %s)", len(gdf), SOURCE_PATH, SOURCE_LAYER)

    source_epsg = gdf.crs.to_epsg()
    if source_epsg != TARGET_SRID:
        raise RuntimeError(f"Unexpected mesh block CRS EPSG:{source_epsg}, expected {TARGET_SRID}")

    rows = []
    null_count = invalid_count = dropped_count = 0
    for _, feat in gdf.iterrows():
        geom, was_invalid, was_dropped = repair_to_multipolygon(feat.geometry)
        if is_missing_geom(feat.geometry):
            null_count += 1
        if was_invalid:
            invalid_count += 1
        if was_dropped:
            dropped_count += 1

        area = feat["AREA_ALBERS_SQKM"]
        wkb = psycopg2.Binary(shapely.to_wkb(geom)) if geom is not None else None

        rows.append((
            CENSUS_YEAR,
            str(feat["MB_CODE_2021"]),
            str(feat["MB_CATEGORY_2021"]),
            str(feat["SA2_CODE_2021"]),
            float(area) if pd.notna(area) else None,
            wkb,
        ))

    repaired_count = invalid_count - dropped_count
    logger.info(
        "%d rows, %d null geom, %d invalid, %d repaired, %d dropped",
        len(rows), null_count, invalid_count, repaired_count, dropped_count,
    )

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM geo.mesh_block WHERE census_year = %s", (CENSUS_YEAR,))

    insert_sql = """
        INSERT INTO geo.mesh_block (census_year, mb_code, mb_category, sa2_code, area_sqkm, geom)
        VALUES %s
    """
    execute_values(
        cur,
        insert_sql,
        rows,
        template="(%s,%s,%s,%s,%s, ST_SetSRID(ST_GeomFromWKB(%s), 7844))",
    )
    conn.commit()
    logger.info("Inserted %d rows into geo.mesh_block", len(rows))

    cur.execute(
        "SELECT DISTINCT ST_SRID(geom) FROM geo.mesh_block WHERE census_year = %s AND geom IS NOT NULL",
        (CENSUS_YEAR,),
    )
    srids = {r[0] for r in cur.fetchall()}
    if srids and srids != {TARGET_SRID}:
        raise RuntimeError(f"unexpected SRID(s) in geo.mesh_block: {srids}")
    logger.info("Verified ST_SRID = %s for all non-null geometries", srids or "{} (all NULL)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    setup_logging("load_mesh_blocks")
    main()
