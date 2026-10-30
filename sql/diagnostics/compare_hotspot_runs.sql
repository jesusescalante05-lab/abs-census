-- =====================================================================
-- compare_hotspot_runs.sql
-- Compares two analysis.hotspot_runs by region_code: gi_star_class,
-- knn_gi_star_class, local_moran_class, knn_local_moran_class, and the
-- derived gi_star_confidence (analysis.gi_star_confidence(), sql/02).
-- Lists every SA2 where anything differs.
--
-- Parameters (substitute before running -- no psql on this machine, so
-- these are plain text placeholders, not psql :variables):
--   {{RUN_A}} -- the earlier run_id
--   {{RUN_B}} -- the later run_id
-- =====================================================================
WITH confidence AS (
    SELECT run_id, region_code, gi_star_class, knn_gi_star_class,
           local_moran_class, knn_local_moran_class,
           analysis.gi_star_confidence(gi_star_class, knn_gi_star_class) AS gi_star_confidence
    FROM analysis.housing_stress_hotspots
    WHERE run_id IN ({{RUN_A}}, {{RUN_B}})
)
SELECT
    s.region_name, a.region_code,
    a.gi_star_class AS a_gi_queen, b.gi_star_class AS b_gi_queen,
    a.knn_gi_star_class AS a_gi_knn, b.knn_gi_star_class AS b_gi_knn,
    a.gi_star_confidence AS a_confidence, b.gi_star_confidence AS b_confidence,
    a.local_moran_class AS a_lisa_queen, b.local_moran_class AS b_lisa_queen,
    a.knn_local_moran_class AS a_lisa_knn, b.knn_local_moran_class AS b_lisa_knn
FROM confidence a
JOIN confidence b ON b.region_code = a.region_code AND a.run_id = {{RUN_A}} AND b.run_id = {{RUN_B}}
JOIN analysis.housing_stress_sa2 s ON s.region_code = a.region_code
WHERE a.gi_star_class         IS DISTINCT FROM b.gi_star_class
   OR a.knn_gi_star_class     IS DISTINCT FROM b.knn_gi_star_class
   OR a.local_moran_class     IS DISTINCT FROM b.local_moran_class
   OR a.knn_local_moran_class IS DISTINCT FROM b.knn_local_moran_class
ORDER BY s.region_name;
