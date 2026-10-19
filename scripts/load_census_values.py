"""Unpivot staged Census DataPack tables into the long/tidy census.value fact table."""

import argparse
import logging
import re
import sys
from pathlib import Path

from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from geo_code_columns import LEVELS, YEARS
from logging_setup import setup_logging

logger = logging.getLogger("load_census_values")

STAGE_TABLE_RE = re.compile(r"^([a-z0-9]+)_(ste|sa2|lga)_(\d{4})$")


def discover_stage_tables(conn, years=None, levels=None, tables=None):
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'stage' ORDER BY table_name")
    found = []
    for (name,) in cur.fetchall():
        m = STAGE_TABLE_RE.match(name)
        if not m:
            continue
        table_code_lower, level_lower, year_str = m.groups()
        year, level, table_id = int(year_str), level_lower.upper(), table_code_lower.upper()
        if years and year not in years:
            continue
        if levels and level not in levels:
            continue
        if tables and table_id not in {t.upper() for t in tables}:
            continue
        found.append((year, level, table_id, name))
    cur.close()
    return found


def stage_columns(conn, table_name):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'stage' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    cols = [r[0] for r in cur.fetchall()]
    cur.close()
    return cols[0], cols[1:]


def resolve_variable_codes(conn, year, table_id, short_codes):
    cur = conn.cursor()
    cur.execute(
        "SELECT short_code, variable_code FROM census.variable WHERE census_year = %s AND table_id = %s",
        (year, table_id),
    )
    lookup = dict(cur.fetchall())
    cur.close()

    resolved, unmatched = [], []
    for short_code in short_codes:
        variable_code = lookup.get(short_code)
        if variable_code is None:
            unmatched.append(short_code)
        else:
            resolved.append((short_code, variable_code))
    return resolved, unmatched


def region_code_expr(geo_col, level, year):
    return sql.SQL(
        "CASE WHEN {level_lit} = 'LGA' THEN regexp_replace(t.{geo_col}, '^LGA', '') ELSE t.{geo_col} END"
    ).format(level_lit=sql.Literal(level), geo_col=sql.Identifier(geo_col))


def find_orphans(conn, table_name, geo_col, year, level):
    table_ident = sql.Identifier("stage", table_name)
    expr = region_code_expr(geo_col, level, year)
    query = sql.SQL(
        """
        SELECT DISTINCT s.region_code FROM (
            SELECT {expr} AS region_code FROM {table_ident} t
        ) s
        WHERE NOT EXISTS (
            SELECT 1 FROM geo.region g
            WHERE g.census_year = {year_lit} AND g.geo_level = {level_lit} AND g.region_code = s.region_code
        )
        """
    ).format(expr=expr, table_ident=table_ident, year_lit=sql.Literal(year), level_lit=sql.Literal(level))
    cur = conn.cursor()
    cur.execute(query)
    orphans = [r[0] for r in cur.fetchall()]
    cur.close()
    return orphans


def insert_values(conn, table_name, geo_col, year, level, resolved):
    if not resolved:
        return 0
    table_ident = sql.Identifier("stage", table_name)
    expr = region_code_expr(geo_col, level, year)
    values_rows = sql.SQL(", ").join(
        sql.SQL("({}, t.{})").format(sql.Literal(variable_code), sql.Identifier(short_code))
        for short_code, variable_code in resolved
    )
    query = sql.SQL(
        """
        WITH src AS (
            SELECT {expr} AS region_code, v.variable_code, v.value
            FROM {table_ident} t
            CROSS JOIN LATERAL (VALUES {values_rows}) AS v(variable_code, value)
        )
        INSERT INTO census.value (census_year, geo_level, region_code, variable_code, value)
        SELECT {year_lit}, {level_lit}, src.region_code, src.variable_code, src.value
        FROM src
        JOIN geo.region g
            ON g.census_year = {year_lit} AND g.geo_level = {level_lit} AND g.region_code = src.region_code
        """
    ).format(
        expr=expr, table_ident=table_ident, values_rows=values_rows,
        year_lit=sql.Literal(year), level_lit=sql.Literal(level),
    )
    cur = conn.cursor()
    cur.execute(query)
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    return inserted


def population_cross_check(conn, year):
    cur = conn.cursor()
    cur.execute(
        "SELECT variable_code FROM census.variable WHERE census_year = %s AND table_id = 'G01' AND short_code = 'Tot_P_P'",
        (year,),
    )
    row = cur.fetchone()
    if row is None:
        logger.warning("%s: no G01/Tot_P_P variable found, skipping population cross-check", year)
        cur.close()
        return
    variable_code = row[0]
    cur.execute(
        """
        SELECT geo_level, SUM(value) FROM census.value
        WHERE census_year = %s AND variable_code = %s AND geo_level IN ('SA2', 'STE')
        GROUP BY geo_level
        """,
        (year, variable_code),
    )
    totals = dict(cur.fetchall())
    cur.close()
    sa2_total, ste_total = totals.get("SA2"), totals.get("STE")
    match = sa2_total is not None and ste_total is not None and sa2_total == ste_total
    logger.info(
        "%s: population cross-check -- SA2 total = %s, STE total = %s, match = %s",
        year, sa2_total, ste_total, match,
    )


def load_all(conn, years=None, levels=None, tables=None):
    stage_tables = discover_stage_tables(conn, years, levels, tables)
    if not stage_tables:
        logger.warning("No matching stage tables found")
        return [], []

    distinct_year_level = sorted({(y, l) for y, l, _, _ in stage_tables})
    cur = conn.cursor()
    for year, level in distinct_year_level:
        cur.execute("DELETE FROM census.value WHERE census_year = %s AND geo_level = %s", (year, level))
    conn.commit()
    cur.close()
    logger.info("Cleared census.value for %d (year, level) pairs before reloading", len(distinct_year_level))

    orphans_by_year_level = {}
    unmatched_columns = []
    years_touched = set()

    for year, level, table_id, table_name in stage_tables:
        years_touched.add(year)
        geo_col, data_cols = stage_columns(conn, table_name)
        resolved, unmatched = resolve_variable_codes(conn, year, table_id, data_cols)
        for short_code in unmatched:
            unmatched_columns.append((year, table_id, short_code))
            logger.warning("%s: no metadata match for column '%s' (table_id=%s)", table_name, short_code, table_id)

        if (year, level) not in orphans_by_year_level:
            orphans = find_orphans(conn, table_name, geo_col, year, level)
            orphans_by_year_level[(year, level)] = orphans
            if orphans:
                logger.warning("%s %s: %d orphan region code(s): %s", year, level, len(orphans), orphans)

        inserted = insert_values(conn, table_name, geo_col, year, level, resolved)
        logger.info("%s: inserted %d rows into census.value", table_name, inserted)

    for year in sorted(years_touched):
        population_cross_check(conn, year)

    all_orphans = [(y, l, code) for (y, l), codes in orphans_by_year_level.items() for code in codes]
    logger.info(
        "Final summary: %d orphan region codes across %d (year,level) pairs; %d unmatched DataPack columns",
        len(all_orphans), sum(1 for codes in orphans_by_year_level.values() if codes), len(unmatched_columns),
    )
    if all_orphans:
        for year, level, code in all_orphans:
            logger.info("  orphan: year=%s level=%s region_code=%s", year, level, code)

    return all_orphans, unmatched_columns


def main():
    parser = argparse.ArgumentParser(description="Unpivot staged DataPack tables into census.value.")
    parser.add_argument("--year", type=int, choices=YEARS)
    parser.add_argument("--level", choices=LEVELS)
    parser.add_argument("--table", action="append", help="Only this table code (e.g. G01). Repeatable.")
    args = parser.parse_args()

    years = [args.year] if args.year else None
    levels = [args.level] if args.level else None

    conn = get_connection()
    try:
        orphans, unmatched = load_all(conn, years, levels, args.table)
    finally:
        conn.close()

    if orphans:
        sys.exit(1)


if __name__ == "__main__":
    setup_logging("load_census_values")
    main()
