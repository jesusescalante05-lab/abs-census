-- =====================================================================
-- 02_fn_gi_star_confidence.sql
-- ADR-002 confidence-class rule, defined once. Used by
-- analysis.housing_stress_hotspots_latest (sql/11) and
-- sql/diagnostics/compare_hotspot_runs.sql, so the rule lives in one
-- place rather than being repeated as an inline CASE in each.
-- =====================================================================

CREATE OR REPLACE FUNCTION analysis.gi_star_confidence(queen_class text, knn_class text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN queen_class IS NULL THEN 'not_analysed'
        WHEN queen_class = 'hotspot'  AND knn_class = 'hotspot'  THEN 'robust_hotspot'
        WHEN queen_class = 'coldspot' AND knn_class = 'coldspot' THEN 'robust_coldspot'
        WHEN (queen_class = 'hotspot'  AND knn_class = 'coldspot')
          OR (queen_class = 'coldspot' AND knn_class = 'hotspot') THEN 'conflicting'
        WHEN queen_class = 'hotspot'  OR knn_class = 'hotspot'  THEN 'possible_hotspot'
        WHEN queen_class = 'coldspot' OR knn_class = 'coldspot' THEN 'possible_coldspot'
        ELSE 'not_significant'
    END;
$$;
