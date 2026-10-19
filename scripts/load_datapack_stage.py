"""Load each ABS Census DataPack CSV as-is into its own stage.<table>_<geo>_<year> table."""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from geo_code_columns import DATAPACK_CODE_COL, LEVELS, YEARS
from logging_setup import setup_logging

logger = logging.getLogger("load_datapack_stage")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FILENAME_RE = re.compile(r"^\d{4}Census_([A-Za-z0-9]+)_AUST?_([A-Z0-9]+)\.csv$")


def pack_dir_for(year, level):
    return DATA_DIR / "raw" / "datapacks" / str(year) / f"{year}_GCP_{level}_for_AUS_short-header"


def iter_datapack_csvs(year, level):
    pack_dir = pack_dir_for(year, level)
    data_dirs = [
        d for d in pack_dir.iterdir()
        if d.is_dir() and d.name not in ("Metadata", "Readme")
    ]
    if len(data_dirs) != 1:
        raise RuntimeError(f"Expected exactly one data folder under {pack_dir}, found {data_dirs}")
    for csv_path in sorted(data_dirs[0].glob("*.csv")):
        match = FILENAME_RE.match(csv_path.name)
        if not match:
            logger.warning("Skipping unrecognized filename: %s", csv_path.name)
            continue
        table_code, geo_in_name = match.groups()
        if geo_in_name != level:
            logger.warning(
                "%s: filename geo suffix '%s' != expected level '%s'",
                csv_path.name, geo_in_name, level,
            )
        yield table_code, csv_path


def read_header(csv_path):
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        return next(reader)


def stage_table_name(table_code, level, year):
    return f"stage.{table_code.lower()}_{level.lower()}_{year}"


def load_one_csv(conn, year, level, table_code, csv_path):
    header = read_header(csv_path)
    table_name = stage_table_name(table_code, level, year)

    geo_col = header[0]
    expected = DATAPACK_CODE_COL.get((year, level))
    if expected and geo_col != expected:
        logger.warning(
            "%s: first column '%s' != expected geo-code column '%s'",
            table_name, geo_col, expected,
        )

    col_defs = [f'"{header[0]}" TEXT'] + [f'"{col}" NUMERIC' for col in header[1:]]

    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    cur.execute(f"CREATE TABLE {table_name} ({', '.join(col_defs)})")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        cur.copy_expert(f"COPY {table_name} FROM STDIN WITH (FORMAT csv, HEADER true)", f)

    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cur.fetchone()[0]
    conn.commit()
    cur.close()

    logger.info("%s: %d columns, %d rows loaded from %s", table_name, len(header), row_count, csv_path.name)
    return table_name


def load_all(conn, years, levels, tables=None):
    loaded = []
    for year in years:
        for level in levels:
            for table_code, csv_path in iter_datapack_csvs(year, level):
                if tables and table_code not in tables:
                    continue
                loaded.append((year, level, table_code, load_one_csv(conn, year, level, table_code, csv_path)))
    return loaded


def main():
    parser = argparse.ArgumentParser(description="Stage ABS Census DataPack CSVs, one table per CSV.")
    parser.add_argument("--year", type=int, choices=YEARS)
    parser.add_argument("--level", choices=LEVELS)
    parser.add_argument("--table", action="append", help="Only this table code (e.g. G01). Repeatable.")
    args = parser.parse_args()

    years = [args.year] if args.year else list(YEARS)
    levels = [args.level] if args.level else list(LEVELS)
    tables = set(args.table) if args.table else None

    conn = get_connection()
    try:
        loaded = load_all(conn, years, levels, tables)
        logger.info("Staged %d tables total", len(loaded))
    finally:
        conn.close()


if __name__ == "__main__":
    setup_logging("load_datapack_stage")
    main()
