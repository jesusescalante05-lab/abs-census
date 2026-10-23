"""Run every ADR-001 validation check against analysis.housing_stress_sa2."""

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection

ALL_PASSED = True


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

    # 1. Returns exactly 185 rows.
    cur.execute("SELECT COUNT(*) FROM analysis.housing_stress_sa2;")
    total = cur.fetchone()[0]
    check("Row count == 185", total == 185, f"got {total}")

    # 2. 165 rows with rent_status='ok' and a non-NULL rent_burden.
    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_sa2 "
        "WHERE rent_status = 'ok' AND rent_burden IS NOT NULL;"
    )
    rent_ok = cur.fetchone()[0]
    check("rent_status='ok' AND rent_burden non-null count == 165", rent_ok == 165, f"got {rent_ok}")

    # 3. mortgage_status='ok' count -- reported, not asserted against a fixed number.
    cur.execute("SELECT COUNT(*) FROM analysis.housing_stress_sa2 WHERE mortgage_status = 'ok';")
    mortgage_ok = cur.fetchone()[0]
    print(f"[INFO] mortgage_status='ok' count (measured, not asserted): {mortgage_ok}")

    # 4. Spot values match the Phase 1 exploration.
    cur.execute(
        "SELECT region_code, ROUND(rent_burden, 3) FROM analysis.housing_stress_sa2 "
        "WHERE region_code IN ('502011025', '503011034');"
    )
    spot = dict(cur.fetchall())
    check(
        "Mandurah (502011025) rent_burden rounds to 0.300",
        spot.get("502011025") == Decimal("0.300"),
        f"got {spot.get('502011025')}",
    )
    check(
        "Mosman Park - Peppermint Grove (503011034) rent_burden rounds to 0.135",
        spot.get("503011034") == Decimal("0.135"),
        f"got {spot.get('503011034')}",
    )

    # 5. No rent_burden or mortgage_burden equals 0.
    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_sa2 "
        "WHERE rent_burden = 0 OR mortgage_burden = 0;"
    )
    zero_count = cur.fetchone()[0]
    check("No rent_burden or mortgage_burden == 0", zero_count == 0, f"got {zero_count}")

    # 6. Every row has geometry.
    cur.execute("SELECT COUNT(*) FROM analysis.housing_stress_sa2 WHERE geom IS NULL;")
    null_geom = cur.fetchone()[0]
    check("Every row has geometry (non-NULL geom)", null_geom == 0, f"got {null_geom}")

    # 7. Consistency: a NULL burden can never have status 'ok', and vice versa.
    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_sa2 "
        "WHERE (rent_burden IS NULL) != (rent_status <> 'ok');"
    )
    rent_inconsistent = cur.fetchone()[0]
    check(
        "rent_burden NULL-ness matches rent_status",
        rent_inconsistent == 0,
        f"{rent_inconsistent} inconsistent row(s)",
    )

    cur.execute(
        "SELECT COUNT(*) FROM analysis.housing_stress_sa2 "
        "WHERE (mortgage_burden IS NULL) != (mortgage_status <> 'ok');"
    )
    mortgage_inconsistent = cur.fetchone()[0]
    check(
        "mortgage_burden NULL-ness matches mortgage_status",
        mortgage_inconsistent == 0,
        f"{mortgage_inconsistent} inconsistent row(s)",
    )

    cur.close()
    conn.close()

    print()
    print("ALL CHECKS PASSED" if ALL_PASSED else "SOME CHECKS FAILED")
    sys.exit(0 if ALL_PASSED else 1)


if __name__ == "__main__":
    main()
