-- =====================================================================
-- 13_analysis_housing_stress_display.sql
-- ADR-003: cartographic display geometry (materialized).
--
-- Depends on analysis.sa2_main_part (sql/12). No CASCADE: if sql/12's
-- definition changes, re-run 12 THEN this file together. For a routine
-- data refresh with no definition change, use scripts/refresh_display.sql
-- instead of re-running either file.
-- =====================================================================

DROP MATERIALIZED VIEW IF EXISTS analysis.housing_stress_display_sa2;

CREATE MATERIALIZED VIEW analysis.housing_stress_display_sa2 AS
WITH residential_dissolved AS (
    -- Residential mesh blocks matched to their SA2 by attribute (not a
    -- spatial join -- avoids boundary slivers), kept only if their
    -- representative point is covered by that SA2's main populated part
    -- (analysis.sa2_main_part), then dissolved into one shape per SA2.
    SELECT
        mb.sa2_code AS region_code,
        ST_Multi(ST_CollectionExtract(ST_Union(mb.geom), 3)) AS display_geom
    FROM geo.mesh_block mb
    JOIN analysis.sa2_main_part mp ON mp.region_code = mb.sa2_code
    WHERE mb.census_year = 2021 AND mb.mb_category = 'Residential'
      AND ST_Covers(mp.part_geom, ST_PointOnSurface(mb.geom))
    GROUP BY mb.sa2_code
)
SELECT region_code, 'residential_mask'::text AS display_type, display_geom
FROM residential_dissolved
UNION ALL
-- Analysed SA2 with zero residential mesh blocks anywhere (e.g. Carabooda -
-- Pinjar): full extent, flagged distinctly from "not analysed".
SELECT g.region_code, 'full_extent_no_residential'::text AS display_type, g.geom AS display_geom
FROM geo.region g
JOIN analysis.housing_stress_sa2 s ON s.region_code = g.region_code
WHERE g.census_year = 2021 AND g.geo_level = 'SA2' AND s.rent_status = 'ok'
  AND g.region_code NOT IN (SELECT region_code FROM residential_dissolved)
UNION ALL
-- Not analysed (ADR-001 R2 exclusion): full extent.
SELECT g.region_code, 'full_extent'::text AS display_type, g.geom AS display_geom
FROM geo.region g
JOIN analysis.housing_stress_sa2 s ON s.region_code = g.region_code
WHERE g.census_year = 2021 AND g.geo_level = 'SA2' AND s.rent_status <> 'ok'
WITH DATA;

CREATE UNIQUE INDEX housing_stress_display_sa2_region_idx ON analysis.housing_stress_display_sa2 (region_code);
CREATE INDEX housing_stress_display_sa2_geom_gix ON analysis.housing_stress_display_sa2 USING gist (display_geom);

COMMENT ON MATERIALIZED VIEW analysis.housing_stress_display_sa2 IS
    'Cartographic display geometry for ADR-003 (materialized -- refresh with '
    'scripts/refresh_display.sql after reloading mesh blocks/boundaries). '
    'display_type: residential_mask (normal case), full_extent_no_residential '
    '(analysed SA2 with zero residential mesh blocks, e.g. Carabooda - Pinjar), '
    'full_extent (not analysed, ADR-001 R2). Geometry only -- join to '
    'analysis.housing_stress_hotspots_latest for gi_star_confidence/rent_burden. '
    'See docs/decisions/ADR-003-cartography.md.';
