-- =====================================================================
-- 12_analysis_sa2_main_part.sql
-- Single source of truth for each analysed SA2's "main populated part":
-- the polygon part with the most Residential mesh blocks, or (if none
-- has any) the largest part by area in EPSG:7850.
--
-- Read by scripts/hotspots_housing_stress.py (KNN representative point)
-- and sql/13_analysis_housing_stress_display.sql (display mask) -- neither
-- computes this independently.
--
-- No CASCADE. sql/13 depends on this view: if you change this file's
-- definition, re-run 12 THEN 13 together (re-running 12 alone will fail
-- with a dependency error if 13 already exists -- that failure is
-- intentional, not a bug, so the coupling can't be missed). For a
-- routine data refresh with no definition change, use
-- scripts/refresh_display.sql instead.
-- =====================================================================

DROP MATERIALIZED VIEW IF EXISTS analysis.sa2_main_part;

CREATE MATERIALIZED VIEW analysis.sa2_main_part AS
WITH analysed AS (
    SELECT region_code FROM analysis.housing_stress_sa2 WHERE rent_status = 'ok'
),
parts AS (
    SELECT g.region_code, (d.path)[1] AS part_index, d.geom AS part_geom
    FROM geo.region g
    CROSS JOIN LATERAL ST_Dump(g.geom) AS d
    WHERE g.census_year = 2021 AND g.geo_level = 'SA2'
      AND g.region_code IN (SELECT region_code FROM analysed)
),
part_counts AS (
    -- ST_Covers(part, point-on-surface-of-mb), not ST_Intersects(mb, part):
    -- assigns each mesh block to exactly one part (its representative point
    -- can only be covered by one of several disjoint SA2 parts), rather than
    -- risking a boundary-touching mesh block counting toward two parts.
    SELECT p.region_code, p.part_index, p.part_geom,
           COUNT(mb.mb_code) AS residential_mb_count,
           ST_Area(ST_Transform(p.part_geom, 7850)) AS area_m2
    FROM parts p
    LEFT JOIN geo.mesh_block mb
        ON mb.census_year = 2021 AND mb.sa2_code = p.region_code AND mb.mb_category = 'Residential'
       AND ST_Covers(p.part_geom, ST_PointOnSurface(mb.geom))
    GROUP BY p.region_code, p.part_index, p.part_geom
),
n_parts AS (
    SELECT region_code, COUNT(*) AS n_parts FROM parts GROUP BY region_code
),
ranked AS (
    SELECT pc.*, np.n_parts,
           MAX(pc.residential_mb_count) OVER (PARTITION BY pc.region_code) AS max_residential_count,
           ROW_NUMBER() OVER (
               PARTITION BY pc.region_code
               ORDER BY pc.residential_mb_count DESC, pc.area_m2 DESC
           ) AS rn
    FROM part_counts pc
    JOIN n_parts np ON np.region_code = pc.region_code
)
SELECT
    region_code,
    part_geom,
    ST_Transform(ST_PointOnSurface(part_geom), 7850) AS representative_point_7850,
    residential_mb_count,
    n_parts,
    CASE WHEN max_residential_count > 0 THEN 'residential_count' ELSE 'largest_area_fallback' END AS rule_used
FROM ranked
WHERE rn = 1
WITH DATA;

CREATE UNIQUE INDEX sa2_main_part_region_idx ON analysis.sa2_main_part (region_code);
CREATE INDEX sa2_main_part_geom_gix ON analysis.sa2_main_part USING gist (part_geom);

COMMENT ON MATERIALIZED VIEW analysis.sa2_main_part IS
    'Single source of truth for each analysed SA2''s main populated part: the '
    'polygon part with the most Residential mesh blocks, or (if none has any) the '
    'largest part by area in EPSG:7850. Read by scripts/hotspots_housing_stress.py '
    '(KNN representative point) and sql/13_analysis_housing_stress_display.sql '
    '(display mask) -- neither computes this independently. Refresh with '
    'REFRESH MATERIALIZED VIEW CONCURRENTLY analysis.sa2_main_part (see '
    'scripts/refresh_display.sql) after reloading geo.mesh_block/geo.region.';
