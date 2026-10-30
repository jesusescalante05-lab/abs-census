"""Run every ADR-003 validation check against analysis.housing_stress_display_sa2."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection

ALL_PASSED = True
ROTTNEST_MB_CODE = "50077840000"
EXPECTED_NO_RESIDENTIAL = {"505031256"}  # Carabooda - Pinjar


def check(label, passed, detail=""):
    global ALL_PASSED
    status = "PASS" if passed else "FAIL"
    suffix = f": {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    if not passed:
        ALL_PASSED = False


def main():
    conn = get_connection()
    cur = conn.cursor()

    # 0. Row count == 185 unconditionally (every analysed + not-analysed SA2
    # now gets exactly one row, via residential_mask, full_extent_no_residential,
    # or full_extent).
    cur.execute("SELECT COUNT(*) FROM analysis.housing_stress_display_sa2;")
    total = cur.fetchone()[0]
    check("Row count == 185", total == 185, f"got {total}")

    # 1. One display shape per analysed SA2 with >=1 qualifying residential
    # mesh block, matching analysis.sa2_main_part's own counts independently.
    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_display_sa2 WHERE display_type = 'residential_mask';"
    )
    mask_rows = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM analysis.sa2_main_part WHERE residential_mb_count > 0;"
    )
    expected_mask_rows = cur.fetchone()[0]
    check(
        "residential_mask row count matches SA2s with residential_mb_count > 0",
        mask_rows == expected_mask_rows,
        f"got {mask_rows}, expected {expected_mask_rows}",
    )

    # 2. No display shape intersects Rottnest Island's mesh block.
    cur.execute(
        """
        SELECT COUNT(*) FROM analysis.housing_stress_display_sa2 d
        WHERE d.display_type = 'residential_mask'
          AND ST_Intersects(d.display_geom, (SELECT geom FROM geo.mesh_block WHERE mb_code = %s));
        """,
        (ROTTNEST_MB_CODE,),
    )
    rottnest_hits = cur.fetchone()[0]
    check(
        f"No display shape intersects Rottnest Island (MB {ROTTNEST_MB_CODE})",
        rottnest_hits == 0,
        f"got {rottnest_hits}",
    )

    # 3. Every display shape lies within its SA2.
    cur.execute(
        """
        SELECT COUNT(*) FROM analysis.housing_stress_display_sa2 d
        JOIN geo.region g ON g.census_year = 2021 AND g.geo_level = 'SA2' AND g.region_code = d.region_code
        WHERE NOT ST_CoveredBy(d.display_geom, g.geom);
        """
    )
    not_covered = cur.fetchone()[0]
    check("Every display shape lies within its SA2 (ST_CoveredBy)", not_covered == 0, f"{not_covered} violation(s)")

    # 4. All 20 not-analysed SA2s present at full extent.
    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_display_sa2 WHERE display_type = 'full_extent';"
    )
    full_extent_count = cur.fetchone()[0]
    check("not-analysed SA2s present at full extent == 20", full_extent_count == 20, f"got {full_extent_count}")

    cur.execute(
        """
        SELECT COUNT(*) FROM analysis.housing_stress_display_sa2 d
        JOIN geo.region g ON g.census_year = 2021 AND g.geo_level = 'SA2' AND g.region_code = d.region_code
        WHERE d.display_type = 'full_extent' AND NOT ST_Equals(d.display_geom, g.geom);
        """
    )
    not_equal = cur.fetchone()[0]
    check(
        "full_extent display shapes are exactly their SA2's geometry (ST_Equals)",
        not_equal == 0,
        f"{not_equal} mismatch(es)",
    )

    # 5. Analysed SA2s with zero residential mesh blocks: flagged distinctly,
    # named, and matching the expected set (Carabooda - Pinjar).
    cur.execute(
        """
        SELECT d.region_code, s.region_name FROM analysis.housing_stress_display_sa2 d
        JOIN analysis.housing_stress_sa2 s ON s.region_code = d.region_code
        WHERE d.display_type = 'full_extent_no_residential'
        ORDER BY d.region_code;
        """
    )
    no_residential = cur.fetchall()
    print(f"[INFO] Analysed SA2s with zero residential mesh blocks ({len(no_residential)}):")
    for region_code, region_name in no_residential:
        print(f"         {region_code}  {region_name}")
    check(
        "full_extent_no_residential SA2s match expected set",
        {rc for rc, _ in no_residential} == EXPECTED_NO_RESIDENTIAL,
        f"got {sorted(rc for rc, _ in no_residential)}",
    )

    # 6. gi_star_confidence class counts among SA2s with a display shape.
    cur.execute(
        """
        SELECT h.gi_star_confidence, COUNT(*)
        FROM analysis.housing_stress_display_sa2 d
        JOIN analysis.housing_stress_hotspots_latest h ON h.region_code = d.region_code
        GROUP BY h.gi_star_confidence
        ORDER BY h.gi_star_confidence;
        """
    )
    print("[INFO] gi_star_confidence counts among SA2s with a display shape:")
    for label, count in cur.fetchall():
        print(f"         {label}: {count}")

    cur.close()
    conn.close()

    print()
    print("ALL CHECKS PASSED" if ALL_PASSED else "SOME CHECKS FAILED")
    sys.exit(0 if ALL_PASSED else 1)


if __name__ == "__main__":
    main()
