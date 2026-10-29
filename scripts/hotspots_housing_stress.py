"""ADR-001 Phase 3: hotspot analysis of rent_burden for Greater Perth SA2s.

Reads the 165 rent_status='ok' rows of analysis.housing_stress_sa2, builds
queen contiguity weights, runs global Moran's I, local Getis-Ord Gi* and
local Moran's I (LISA) with FDR-corrected significance, repeats the two
local statistics on k=6 nearest-neighbour weights as a sensitivity check,
and writes everything to analysis.hotspot_runs / analysis.housing_stress_hotspots.
"""

import logging
import subprocess
import sys
import warnings
from pathlib import Path

import esda
import geopandas as gpd
import libpysal
import numpy as np
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection
from logging_setup import setup_logging

logger = logging.getLogger("hotspots_housing_stress")

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED = 12345
PERMUTATIONS = 9999
ALPHA = 0.05
KNN_K = 6
KNN_CRS = "EPSG:7850"  # GDA2020 / MGA zone 50 -- metres, covers Perth
INDICATOR = "rent_burden"
SOURCE_VIEW = "analysis.housing_stress_sa2"
FILTER_RULE = "rent_status = 'ok'"


def check_git_clean():
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    dirty = [line for line in result.stdout.splitlines() if not line.startswith("??")]
    if dirty:
        print("ERROR: uncommitted changes to tracked files -- commit or stash first:", file=sys.stderr)
        for line in dirty:
            print(" ", line, file=sys.stderr)
        sys.exit(1)


def git_commit_hash():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def load_units(conn):
    sql = f"""
        SELECT region_code, region_name, rent_burden, geom
        FROM {SOURCE_VIEW}
        WHERE {FILTER_RULE}
        ORDER BY region_code
    """
    gdf = gpd.read_postgis(sql, conn, geom_col="geom")
    gdf = gdf.set_index("region_code")
    return gdf


def build_queen_weights(gdf):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        w = libpysal.weights.Queen.from_dataframe(gdf, use_index=True)
        for warning in caught:
            logger.warning("libpysal warning building queen weights: %s", warning.message)
    return w


def build_knn_weights(gdf):
    gdf_proj = gdf.to_crs(KNN_CRS)

    def largest_part_point(geom):
        if geom.geom_type == "Polygon":
            return geom.representative_point()
        largest = max(geom.geoms, key=lambda g: g.area)
        return largest.representative_point()

    points = gdf_proj.geometry.apply(largest_part_point)
    points_gdf = gpd.GeoDataFrame(geometry=points, crs=KNN_CRS, index=gdf_proj.index)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        w = libpysal.weights.KNN.from_dataframe(points_gdf, k=KNN_K, use_index=True)
        for warning in caught:
            logger.warning("libpysal warning building knn weights: %s", warning.message)
    return w


def classify_gi_star(gi, cutoff):
    classes = []
    for z, p in zip(gi.Zs, gi.p_sim):
        if p < cutoff and z > 0:
            classes.append("hotspot")
        elif p < cutoff and z < 0:
            classes.append("coldspot")
        else:
            classes.append("not_significant")
    return classes


QUADRANT_LABELS = {1: "HH", 2: "LH", 3: "LL", 4: "HL"}


def classify_local_moran(lisa, cutoff):
    classes = []
    quadrants = []
    for q, p in zip(lisa.q, lisa.p_sim):
        quadrant = QUADRANT_LABELS[q]
        quadrants.append(quadrant)
        if p >= cutoff:
            classes.append("not_significant")
        elif quadrant == "HH":
            classes.append("hotspot")
        elif quadrant == "LL":
            classes.append("coldspot")
        else:
            classes.append("spatial_outlier")
    return classes, quadrants


def run_local_stats(y, w):
    gi = esda.G_Local(y, w, transform="R", star=True, permutations=PERMUTATIONS, seed=SEED)
    lisa = esda.Moran_Local(y, w, transformation="r", permutations=PERMUTATIONS, seed=SEED)
    gi_cutoff = esda.fdr(gi.p_sim, ALPHA)
    lisa_cutoff = esda.fdr(lisa.p_sim, ALPHA)
    gi_class = classify_gi_star(gi, gi_cutoff)
    lisa_class, lisa_quadrant = classify_local_moran(lisa, lisa_cutoff)
    return {
        "gi": gi, "lisa": lisa,
        "gi_cutoff": gi_cutoff, "lisa_cutoff": lisa_cutoff,
        "gi_class": gi_class, "lisa_class": lisa_class, "lisa_quadrant": lisa_quadrant,
    }


def count_classes(classes, labels):
    return {label: classes.count(label) for label in labels}


def main():
    check_git_clean()

    conn = get_connection()
    gdf = load_units(conn)
    n_units = len(gdf)
    logger.info("Loaded %d units from %s WHERE %s", n_units, SOURCE_VIEW, FILTER_RULE)
    logger.info("seed=%d permutations=%d alpha=%s knn_k=%d", SEED, PERMUTATIONS, ALPHA, KNN_K)

    y = gdf["rent_burden"].to_numpy()

    # --- Weights -----------------------------------------------------
    w_queen = build_queen_weights(gdf)
    logger.info(
        "Queen contiguity: %d units, %d islands%s",
        w_queen.n, len(w_queen.islands),
        f" ({w_queen.islands})" if w_queen.islands else "",
    )
    if w_queen.islands:
        logger.warning("Excluding islands from all statistics: %s", w_queen.islands)
        analysis_gdf = gdf.drop(index=w_queen.islands)
        y = analysis_gdf["rent_burden"].to_numpy()
        w_queen = build_queen_weights(analysis_gdf)
    else:
        analysis_gdf = gdf

    w_knn = build_knn_weights(analysis_gdf)
    logger.info("KNN (k=%d) weights built on %s, largest-part representative points", KNN_K, KNN_CRS)

    # --- Global Moran's I ---------------------------------------------
    np.random.seed(SEED)  # esda.Moran has no seed= kwarg; it draws from the global RNG state
    moran = esda.Moran(y, w_queen, transformation="r", permutations=PERMUTATIONS)
    logger.info(
        "Global Moran's I: I=%.4f  z_sim=%.4f  p_sim=%.4f",
        moran.I, moran.z_sim, moran.p_sim,
    )

    # --- Local statistics, queen weights -------------------------------
    queen_result = run_local_stats(y, w_queen)
    logger.info("Gi* (queen) FDR cutoff: %.6g", queen_result["gi_cutoff"])
    logger.info("Local Moran (queen) FDR cutoff: %.6g", queen_result["lisa_cutoff"])
    gi_queen_counts = count_classes(queen_result["gi_class"], ["hotspot", "coldspot", "not_significant"])
    lisa_queen_counts = count_classes(
        queen_result["lisa_class"], ["hotspot", "coldspot", "spatial_outlier", "not_significant"]
    )
    logger.info("Gi* (queen) classes: %s", gi_queen_counts)
    logger.info("Local Moran (queen) classes: %s", lisa_queen_counts)

    # --- Local statistics, knn sensitivity check -----------------------
    knn_result = run_local_stats(y, w_knn)
    gi_knn_counts = count_classes(knn_result["gi_class"], ["hotspot", "coldspot", "not_significant"])
    lisa_knn_counts = count_classes(
        knn_result["lisa_class"], ["hotspot", "coldspot", "spatial_outlier", "not_significant"]
    )
    logger.info("Gi* (knn) classes: %s", gi_knn_counts)
    logger.info("Local Moran (knn) classes: %s", lisa_knn_counts)

    gi_changed = [a != b for a, b in zip(queen_result["gi_class"], knn_result["gi_class"])]
    lisa_changed = [a != b for a, b in zip(queen_result["lisa_class"], knn_result["lisa_class"])]
    gi_changed_count = sum(gi_changed)
    lisa_changed_count = sum(lisa_changed)
    logger.info("Gi* class changed (queen -> knn): %d / %d", gi_changed_count, len(analysis_gdf))
    logger.info("Local Moran class changed (queen -> knn): %d / %d", lisa_changed_count, len(analysis_gdf))
    region_codes = list(analysis_gdf.index)
    for i, region_code in enumerate(region_codes):
        if gi_changed[i]:
            logger.info(
                "  Gi* changed: %s (%s): queen=%s knn=%s",
                region_code, analysis_gdf.loc[region_code, "region_name"],
                queen_result["gi_class"][i], knn_result["gi_class"][i],
            )
    for i, region_code in enumerate(region_codes):
        if lisa_changed[i]:
            logger.info(
                "  Local Moran changed: %s (%s): queen=%s knn=%s",
                region_code, analysis_gdf.loc[region_code, "region_name"],
                queen_result["lisa_class"][i], knn_result["lisa_class"][i],
            )

    # --- Persist -------------------------------------------------------
    commit = git_commit_hash()
    logger.info("code_commit=%s", commit)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO analysis.hotspot_runs (
            indicator, source_view, filter_rule, n_units, alpha, knn_k, code_commit,
            seed, permutations, libpysal_version, esda_version, weights_methods,
            queen_n_islands, global_moran_i, global_moran_z_sim, global_moran_p_sim,
            gi_star_queen_fdr_cutoff, local_moran_queen_fdr_cutoff,
            gi_star_knn_fdr_cutoff, local_moran_knn_fdr_cutoff,
            gi_star_queen_hotspot_count, gi_star_queen_coldspot_count,
            gi_star_knn_hotspot_count, gi_star_knn_coldspot_count,
            local_moran_queen_hotspot_count, local_moran_queen_coldspot_count, local_moran_queen_outlier_count,
            local_moran_knn_hotspot_count, local_moran_knn_coldspot_count, local_moran_knn_outlier_count,
            gi_star_class_changed_count, local_moran_class_changed_count
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s
        ) RETURNING run_id
        """,
        (
            INDICATOR, SOURCE_VIEW, FILTER_RULE, len(analysis_gdf), ALPHA, KNN_K, commit,
            SEED, PERMUTATIONS, libpysal.__version__, esda.__version__,
            "queen contiguity; knn (k=6, MGA zone 50, largest-part representative point)",
            len(w_queen.islands) if hasattr(w_queen, "islands") else 0,
            float(moran.I), float(moran.z_sim), float(moran.p_sim),
            float(queen_result["gi_cutoff"]), float(queen_result["lisa_cutoff"]),
            float(knn_result["gi_cutoff"]), float(knn_result["lisa_cutoff"]),
            gi_queen_counts["hotspot"], gi_queen_counts["coldspot"],
            gi_knn_counts["hotspot"], gi_knn_counts["coldspot"],
            lisa_queen_counts["hotspot"], lisa_queen_counts["coldspot"], lisa_queen_counts["spatial_outlier"],
            lisa_knn_counts["hotspot"], lisa_knn_counts["coldspot"], lisa_knn_counts["spatial_outlier"],
            gi_changed_count, lisa_changed_count,
        ),
    )
    run_id = cur.fetchone()[0]
    logger.info("Inserted analysis.hotspot_runs run_id=%d", run_id)

    rows = []
    for i, region_code in enumerate(analysis_gdf.index):
        rows.append((
            run_id, region_code,
            w_queen.cardinalities[region_code],
            float(queen_result["gi"].Zs[i]), float(queen_result["gi"].p_sim[i]), queen_result["gi_class"][i],
            float(queen_result["lisa"].Is[i]), float(queen_result["lisa"].z_sim[i]), float(queen_result["lisa"].p_sim[i]),
            queen_result["lisa_quadrant"][i], queen_result["lisa_class"][i],
            knn_result["gi_class"][i], knn_result["lisa_class"][i],
            bool(gi_changed[i]), bool(lisa_changed[i]),
        ))

    execute_values(
        cur,
        """
        INSERT INTO analysis.housing_stress_hotspots (
            run_id, region_code, queen_n_neighbors,
            gi_star_z, gi_star_p_sim, gi_star_class,
            local_moran_i, local_moran_z, local_moran_p_sim, local_moran_quadrant, local_moran_class,
            knn_gi_star_class, knn_local_moran_class,
            gi_star_class_changed, local_moran_class_changed
        ) VALUES %s
        """,
        rows,
    )
    conn.commit()
    logger.info("Inserted %d rows into analysis.housing_stress_hotspots (run_id=%d)", len(rows), run_id)

    cur.close()
    conn.close()


if __name__ == "__main__":
    setup_logging("hotspots_housing_stress")
    main()
