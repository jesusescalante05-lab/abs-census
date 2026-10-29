"""Run every ADR-002 validation check against analysis.housing_stress_hotspots_latest."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection

ALL_PASSED = True

EXPECTED_RUN_ID = 1

EXPECTED_CONFIDENCE_COUNTS = {
    "robust_hotspot": 5,
    "possible_hotspot": 4,
    "robust_coldspot": 1,
    "possible_coldspot": 4,
    "conflicting": 0,
    "not_analysed": 20,
    "not_significant": 151,
}

EXPECTED_ROBUST_HOTSPOTS = {
    "Mandurah",
    "Greenfields",
    "Mandurah - South",
    "Mandurah - East",
    "Mandurah - North",
}


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

    # 0. The expected counts below are pinned to run 1 (ADR-002's documented
    # results). If the latest run has moved on, those expectations are stale.
    cur.execute(
        "SELECT run_id FROM analysis.hotspot_runs WHERE indicator = 'rent_burden' "
        "ORDER BY run_id DESC LIMIT 1;"
    )
    row = cur.fetchone()
    latest_run_id = row[0] if row else None
    check(
        f"Latest rent_burden run_id == {EXPECTED_RUN_ID}",
        latest_run_id == EXPECTED_RUN_ID,
        f"got {latest_run_id} -- the expected values below belong to run {EXPECTED_RUN_ID}; "
        f"ADR-002 must be updated (new Results section) before this check means anything for a new run",
    )

    # 1. Row count == 185.
    cur.execute("SELECT COUNT(*) FROM analysis.housing_stress_hotspots_latest;")
    total = cur.fetchone()[0]
    check("Row count == 185", total == 185, f"got {total}")

    # 2. gi_star_confidence class counts match ADR-002's documented run-1 results.
    cur.execute(
        "SELECT gi_star_confidence, COUNT(*) FROM analysis.housing_stress_hotspots_latest "
        "GROUP BY gi_star_confidence;"
    )
    actual_counts = dict(cur.fetchall())
    for label, expected in EXPECTED_CONFIDENCE_COUNTS.items():
        got = actual_counts.get(label, 0)
        check(f"gi_star_confidence='{label}' count == {expected}", got == expected, f"got {got}")

    # 3. The five robust_hotspot SA2s are exactly the ones ADR-002 names.
    cur.execute(
        "SELECT region_name FROM analysis.housing_stress_hotspots_latest "
        "WHERE gi_star_confidence = 'robust_hotspot';"
    )
    actual_robust = {r[0] for r in cur.fetchall()}
    check(
        "robust_hotspot SA2s match ADR-002 by name",
        actual_robust == EXPECTED_ROBUST_HOTSPOTS,
        f"got {sorted(actual_robust)}",
    )

    # 4. not_analysed count lines up with ADR-001's own exclusion rule, not just a row-count coincidence.
    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_hotspots_latest "
        "WHERE (gi_star_confidence = 'not_analysed') != (rent_status <> 'ok');"
    )
    inconsistent = cur.fetchone()[0]
    check(
        "not_analysed matches rent_status <> 'ok'",
        inconsistent == 0,
        f"{inconsistent} inconsistent row(s)",
    )

    cur.close()
    conn.close()

    print()
    print("ALL CHECKS PASSED" if ALL_PASSED else "SOME CHECKS FAILED")
    sys.exit(0 if ALL_PASSED else 1)


if __name__ == "__main__":
    main()
