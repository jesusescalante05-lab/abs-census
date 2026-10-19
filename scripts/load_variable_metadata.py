"""Load Census DataPack variable metadata (Cell Descriptors) into census.variable."""

import argparse
import logging
import sys
from pathlib import Path

import openpyxl
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from geo_code_columns import YEARS
from logging_setup import setup_logging

logger = logging.getLogger("load_variable_metadata")

METADATA_PATH = {
    2016: "data/raw/datapacks/2016/2016_GCP_STE_for_AUS_short-header/Metadata/Metadata_2016_GCP_DataPack.xlsx",
    2021: "data/raw/datapacks/2021/2021_GCP_STE_for_AUS_short-header/Metadata/Metadata_2021_GCP_DataPack_R1_R2.xlsx",
}


def normalize_header(cell):
    return str(cell).strip().lower().replace(" ", "") if cell is not None else ""


def parse_metadata(path):
    """Returns a list of (variable_code, table_id, short_code, long_descriptor)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet_name = next(
        s for s in wb.sheetnames if "cell descriptors" in s.strip().lower()
    )
    ws = wb[sheet_name]

    col_index = None
    rows = []
    for row in ws.iter_rows(values_only=True):
        normalized = [normalize_header(c) for c in row]
        if col_index is None:
            if "sequential" in normalized and "short" in normalized:
                col_index = {name: idx for idx, name in enumerate(normalized) if name}
            continue

        seq = row[col_index["sequential"]]
        short = row[col_index["short"]]
        long_ = row[col_index["long"]]
        table_id = row[col_index["datapackfile"]]
        if seq is None or short is None or table_id is None:
            continue
        rows.append((
            str(seq).strip(),
            str(table_id).strip(),
            str(short).strip(),
            str(long_).strip() if long_ is not None else None,
        ))

    if col_index is None:
        raise RuntimeError(f"Could not find Sequential/Short header row in {path}")

    wb.close()
    return rows


def check_collisions(rows, year):
    seen = {}
    collisions = []
    for variable_code, table_id, short_code, _ in rows:
        key = (table_id, short_code)
        if key in seen and seen[key] != variable_code:
            collisions.append((key, seen[key], variable_code))
        seen[key] = variable_code
    if collisions:
        logger.warning(
            "%s: %d (table_id, short_code) collisions found: %s",
            year, len(collisions), collisions[:10],
        )
    return collisions


def load_one(conn, year):
    path = METADATA_PATH[year]
    logger.info("Reading metadata for %s from %s", year, path)
    rows = parse_metadata(path)
    logger.info("%s: parsed %d variable rows", year, len(rows))

    collisions = check_collisions(rows, year)
    if collisions:
        raise RuntimeError(
            f"{year}: {len(collisions)} (table_id, short_code) collisions in metadata — "
            "cannot safely resolve DataPack columns to variable_code"
        )

    values = [(year, variable_code, table_id, short_code, long_desc)
              for variable_code, table_id, short_code, long_desc in rows]

    cur = conn.cursor()
    cur.execute("DELETE FROM census.variable WHERE census_year = %s", (year,))
    execute_values(
        cur,
        """
        INSERT INTO census.variable
            (census_year, variable_code, table_id, short_code, long_descriptor)
        VALUES %s
        """,
        values,
    )
    conn.commit()
    logger.info("%s: inserted %d rows into census.variable", year, len(values))
    cur.close()


def main():
    parser = argparse.ArgumentParser(description="Load Census DataPack variable metadata.")
    parser.add_argument("--year", type=int, choices=YEARS)
    args = parser.parse_args()

    years = [args.year] if args.year else list(YEARS)

    conn = get_connection()
    try:
        for year in years:
            load_one(conn, year)
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging("load_variable_metadata")
    main()
