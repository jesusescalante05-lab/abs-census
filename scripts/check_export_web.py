"""Validate the Phase 5 web export (scripts/export_web.py outputs)."""

import json
import sys
from pathlib import Path

import pyogrio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_hotspots import EXPECTED_CONFIDENCE_COUNTS, EXPECTED_RUN_ID
from db import get_connection

ALL_PASSED = True
OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "public" / "data"


def check(label, passed, detail=""):
    global ALL_PASSED
    status = "PASS" if passed else "FAIL"
    suffix = f": {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    if not passed:
        ALL_PASSED = False


def reject_nonfinite(constant):
    raise ValueError(f"invalid (non-finite) JSON constant encountered: {constant}")


def load_json_strict(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f, parse_constant=reject_nonfinite)


def main():
    conn = get_connection()
    cur = conn.cursor()

    # --- Vector tiles: 185 distinct source SA2s ------------------------
    # pyogrio.read_info's "features" count, for a tiled format, counts
    # per-tile feature instances across the whole zoom pyramid (the same
    # source feature appears in multiple tiles/zoom levels) -- not the
    # distinct source-feature count. Read the tiles back and count
    # distinct region_code instead.
    display_gdf = None
    for name, layer in (("sa2_display.pmtiles", "sa2_display"), ("sa2_outline.pmtiles", "sa2_outline")):
        path = OUT_DIR / name
        gdf = pyogrio.read_dataframe(str(path), layer=layer)
        n_distinct = gdf["region_code"].nunique()
        check(f"{name}: 185 distinct region_code values", n_distinct == 185, f"got {n_distinct} (from {len(gdf)} tile-feature rows)")
        print(f"[INFO] {name}: {path.stat().st_size} bytes")
        if name == "sa2_display.pmtiles":
            display_gdf = gdf

    # --- rent_burden_quintile: no rent_burden value spans two classes --
    # NTILE(5) assigns buckets by row ORDER, not by value -- a tie exactly
    # at a bucket boundary could land some equal-valued rows in one
    # quintile and others in the next. Check the actually-exported tiles,
    # not a fresh query, so this validates what ships.
    distinct_display = display_gdf.drop_duplicates(subset="region_code")[
        ["region_code", "region_name", "rent_burden", "rent_burden_quintile"]
    ]
    valid_display = distinct_display.dropna(subset=["rent_burden_quintile"])
    quintiles_per_value = valid_display.groupby("rent_burden")["rent_burden_quintile"].nunique()
    tied_values = quintiles_per_value[quintiles_per_value > 1]
    if len(tied_values) > 0:
        tied_rows = valid_display[valid_display["rent_burden"].isin(tied_values.index)].sort_values(
            ["rent_burden", "rent_burden_quintile"]
        )
        detail = "; ".join(
            f"{r.region_code} ({r.region_name}) rent_burden={r.rent_burden} quintile={r.rent_burden_quintile}"
            for r in tied_rows.itertuples()
        )
    else:
        detail = ""
    check(
        "No rent_burden value spans more than one rent_burden_quintile",
        len(tied_values) == 0,
        detail,
    )

    # --- sa2_points.geojson: strict JSON, 185 features ------------------
    try:
        points = load_json_strict(OUT_DIR / "sa2_points.geojson")
        check("sa2_points.geojson parses as strict JSON (no NaN/Infinity)", True)
    except ValueError as exc:
        check("sa2_points.geojson parses as strict JSON (no NaN/Infinity)", False, str(exc))
        points = {"features": []}
    n_points = len(points.get("features", []))
    check("sa2_points.geojson: 185 features", n_points == 185, f"got {n_points}")
    print(f"[INFO] sa2_points.geojson: {(OUT_DIR / 'sa2_points.geojson').stat().st_size} bytes")

    # --- sa2_details.json: strict JSON, 185 records, class counts ------
    try:
        details = load_json_strict(OUT_DIR / "sa2_details.json")
        check("sa2_details.json parses as strict JSON (no NaN/Infinity)", True)
    except ValueError as exc:
        check("sa2_details.json parses as strict JSON (no NaN/Infinity)", False, str(exc))
        details = []
    check("sa2_details.json: 185 records", len(details) == 185, f"got {len(details)}")

    actual_region_codes = {rec["region_code"] for rec in details}
    cur.execute("SELECT region_code FROM analysis.housing_stress_hotspots_latest;")
    expected_region_codes = {r[0] for r in cur.fetchall()}
    check(
        "sa2_details.json region_codes match housing_stress_hotspots_latest exactly",
        actual_region_codes == expected_region_codes,
        f"{len(actual_region_codes.symmetric_difference(expected_region_codes))} mismatched",
    )

    actual_counts = {}
    for rec in details:
        actual_counts[rec["gi_star_confidence"]] = actual_counts.get(rec["gi_star_confidence"], 0) + 1
    for label, expected in EXPECTED_CONFIDENCE_COUNTS.items():
        got = actual_counts.get(label, 0)
        check(f"sa2_details.json gi_star_confidence='{label}' count == {expected}", got == expected, f"got {got}")
    print(f"[INFO] sa2_details.json: {(OUT_DIR / 'sa2_details.json').stat().st_size} bytes")

    # --- run_metadata.json: strict JSON, run_id, quintiles, bbox -------
    try:
        metadata = load_json_strict(OUT_DIR / "run_metadata.json")
        check("run_metadata.json parses as strict JSON (no NaN/Infinity)", True)
    except ValueError as exc:
        check("run_metadata.json parses as strict JSON (no NaN/Infinity)", False, str(exc))
        metadata = {}

    check(
        f"run_metadata.json run_id == {EXPECTED_RUN_ID}",
        metadata.get("run_id") == EXPECTED_RUN_ID,
        f"got {metadata.get('run_id')}",
    )

    cur.execute("SELECT code_commit FROM analysis.hotspot_runs WHERE run_id = %s;", (EXPECTED_RUN_ID,))
    row = cur.fetchone()
    expected_commit = row[0] if row else None
    check(
        "run_metadata.json code_commit matches analysis.hotspot_runs",
        metadata.get("code_commit") == expected_commit,
        f"got {metadata.get('code_commit')!r}, expected {expected_commit!r}",
    )

    breaks = metadata.get("rent_burden_quintile_breaks", [])
    check("run_metadata.json rent_burden_quintile_breaks: 5 values", len(breaks) == 5, f"got {len(breaks)}")
    check(
        "run_metadata.json rent_burden_quintile_breaks: strictly increasing",
        breaks == sorted(breaks) and len(set(breaks)) == len(breaks),
        f"got {breaks}",
    )

    bbox = metadata.get("robust_hotspot_bbox_4326", [])
    check("run_metadata.json robust_hotspot_bbox_4326: 4 values", len(bbox) == 4, f"got {bbox}")
    if len(bbox) == 4:
        minx, miny, maxx, maxy = bbox
        check(
            "run_metadata.json robust_hotspot_bbox_4326: minx < maxx and miny < maxy",
            minx < maxx and miny < maxy,
            f"got {bbox}",
        )
    print(f"[INFO] run_metadata.json: {(OUT_DIR / 'run_metadata.json').stat().st_size} bytes")

    cur.close()
    conn.close()

    print()
    print("ALL CHECKS PASSED" if ALL_PASSED else "SOME CHECKS FAILED")
    sys.exit(0 if ALL_PASSED else 1)


if __name__ == "__main__":
    main()
