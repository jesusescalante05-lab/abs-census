"""Run the full ABS Census load: boundaries -> variable metadata -> stage -> values."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from geo_code_columns import LEVELS, YEARS
from load_boundaries import load_one as load_one_boundary
from load_boundaries import log_datum_transform
from load_census_values import load_all as load_all_values
from load_datapack_stage import load_all as stage_all
from load_variable_metadata import load_one as load_one_variable_metadata
from logging_setup import setup_logging

logger = logging.getLogger("load_all")


def main():
    conn = get_connection()
    try:
        logger.info("=== Step 1/4: boundaries ===")
        for year in YEARS:
            log_datum_transform(year)
        for year in YEARS:
            for level in LEVELS:
                load_one_boundary(conn, year, level)

        logger.info("=== Step 2/4: variable metadata ===")
        for year in YEARS:
            load_one_variable_metadata(conn, year)

        logger.info("=== Step 3/4: stage DataPack CSVs ===")
        staged = stage_all(conn, list(YEARS), list(LEVELS))
        logger.info("Staged %d tables total", len(staged))

        logger.info("=== Step 4/4: unpivot into census.value ===")
        orphans, unmatched = load_all_values(conn)
    finally:
        conn.close()

    if orphans:
        logger.error("Load finished with %d orphan region codes -- see summary above", len(orphans))
        sys.exit(1)

    logger.info("Load finished cleanly (%d unmatched DataPack columns logged as warnings)", len(unmatched))


if __name__ == "__main__":
    setup_logging("load_all")
    main()
