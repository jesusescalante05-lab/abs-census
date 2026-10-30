-- =====================================================================
-- refresh_display.sql
-- Refreshes the ADR-003 display-geometry materialized views after
-- reloading geo.mesh_block / geo.region / analysis.housing_stress_sa2,
-- with no change to either view's definition. sa2_main_part first --
-- housing_stress_display_sa2 reads from it. No CASCADE.
--
-- If you're changing either view's DEFINITION instead, don't use this --
-- re-run sql/12_analysis_sa2_main_part.sql then
-- sql/13_analysis_housing_stress_display.sql directly.
-- =====================================================================
REFRESH MATERIALIZED VIEW CONCURRENTLY analysis.sa2_main_part;
REFRESH MATERIALIZED VIEW CONCURRENTLY analysis.housing_stress_display_sa2;
