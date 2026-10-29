-- =====================================================================
-- 11_analysis_housing_stress_hotspots.sql
-- ADR-001 Phase 3: hotspot-analysis run metadata + per-SA2 results.
-- Idempotent (CREATE TABLE IF NOT EXISTS) -- does not wipe prior runs.
-- Run once before scripts/hotspots_housing_stress.py.
-- =====================================================================

CREATE TABLE IF NOT EXISTS analysis.hotspot_runs (
    run_id                           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_at                           timestamptz NOT NULL DEFAULT now(),
    indicator                        text NOT NULL,              -- e.g. 'rent_burden'
    source_view                      text NOT NULL,              -- e.g. 'analysis.housing_stress_sa2'
    filter_rule                      text NOT NULL,              -- e.g. "rent_status = 'ok'"
    n_units                          integer NOT NULL,           -- e.g. 165
    alpha                            double precision NOT NULL,  -- e.g. 0.05
    knn_k                            integer NOT NULL,           -- e.g. 6
    code_commit                      text NOT NULL,              -- `git rev-parse HEAD` at run time
    seed                             integer NOT NULL,
    permutations                     integer NOT NULL,
    libpysal_version                 text NOT NULL,
    esda_version                     text NOT NULL,
    weights_methods                  text NOT NULL,
    queen_n_islands                  integer NOT NULL,
    global_moran_i                   double precision NOT NULL,
    global_moran_z_sim               double precision NOT NULL,
    global_moran_p_sim               double precision NOT NULL,
    gi_star_queen_fdr_cutoff         double precision NOT NULL,
    local_moran_queen_fdr_cutoff     double precision NOT NULL,
    gi_star_knn_fdr_cutoff           double precision NOT NULL,
    local_moran_knn_fdr_cutoff       double precision NOT NULL,
    gi_star_queen_hotspot_count      integer NOT NULL,
    gi_star_queen_coldspot_count     integer NOT NULL,
    gi_star_knn_hotspot_count        integer NOT NULL,
    gi_star_knn_coldspot_count       integer NOT NULL,
    local_moran_queen_hotspot_count  integer NOT NULL,
    local_moran_queen_coldspot_count integer NOT NULL,
    local_moran_queen_outlier_count  integer NOT NULL,
    local_moran_knn_hotspot_count    integer NOT NULL,
    local_moran_knn_coldspot_count   integer NOT NULL,
    local_moran_knn_outlier_count    integer NOT NULL,
    gi_star_class_changed_count      integer NOT NULL,
    local_moran_class_changed_count  integer NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis.housing_stress_hotspots (
    run_id                    bigint NOT NULL REFERENCES analysis.hotspot_runs (run_id),
    region_code               text   NOT NULL,
    queen_n_neighbors         integer,
    gi_star_z                 double precision,
    gi_star_p_sim             double precision,
    gi_star_class             text,
    local_moran_i             double precision,
    local_moran_z             double precision,
    local_moran_p_sim         double precision,
    local_moran_quadrant      text,
    local_moran_class         text,
    knn_gi_star_class         text,
    knn_local_moran_class     text,
    gi_star_class_changed     boolean,
    local_moran_class_changed boolean,

    PRIMARY KEY (run_id, region_code)
);

-- One row per Greater Perth SA2 (all 185, including the 20 excluded from
-- hotspot analysis), joined to the latest 'rent_burden' run. Excluded SA2s
-- get NULL hotspot fields via the LEFT JOIN. This is what the map queries.
DROP VIEW IF EXISTS analysis.housing_stress_hotspots_latest;

CREATE VIEW analysis.housing_stress_hotspots_latest AS
WITH latest_run AS (
    SELECT run_id
    FROM analysis.hotspot_runs
    WHERE indicator = 'rent_burden'
    ORDER BY run_id DESC
    LIMIT 1
)
SELECT
    s.region_code, s.region_name, s.households, s.renting, s.mortgaged,
    s.rent_status, s.mortgage_status, s.rent_burden, s.mortgage_burden,
    s.renter_share, s.social_housing_share,
    h.run_id, h.queen_n_neighbors,
    h.gi_star_z, h.gi_star_p_sim, h.gi_star_class,
    h.local_moran_i, h.local_moran_z, h.local_moran_p_sim, h.local_moran_quadrant, h.local_moran_class,
    h.knn_gi_star_class, h.knn_local_moran_class,
    h.gi_star_class_changed, h.local_moran_class_changed,
    -- ADR-002 confidence class: agreement between queen and knn Gi* results.
    CASE
        WHEN h.gi_star_class IS NULL THEN 'not_analysed'                                   -- ADR-001 R2 exclusion
        WHEN h.gi_star_class = 'hotspot'  AND h.knn_gi_star_class = 'hotspot'  THEN 'robust_hotspot'
        WHEN h.gi_star_class = 'coldspot' AND h.knn_gi_star_class = 'coldspot' THEN 'robust_coldspot'
        WHEN (h.gi_star_class = 'hotspot'  AND h.knn_gi_star_class = 'coldspot')
          OR (h.gi_star_class = 'coldspot' AND h.knn_gi_star_class = 'hotspot') THEN 'conflicting'
        WHEN h.gi_star_class = 'hotspot'  OR h.knn_gi_star_class = 'hotspot'  THEN 'possible_hotspot'
        WHEN h.gi_star_class = 'coldspot' OR h.knn_gi_star_class = 'coldspot' THEN 'possible_coldspot'
        ELSE 'not_significant'
    END AS gi_star_confidence,
    s.geom
FROM analysis.housing_stress_sa2 s
LEFT JOIN latest_run lr ON true
LEFT JOIN analysis.housing_stress_hotspots h
    ON h.region_code = s.region_code AND h.run_id = lr.run_id;

COMMENT ON VIEW analysis.housing_stress_hotspots_latest IS
    'Latest rent_burden hotspot-analysis run, one row per Greater Perth SA2 (all 185). '
    'Implements docs/decisions/ADR-001-housing-cost-burden.md (indicator, scope, exclusions) '
    'and docs/decisions/ADR-002-hotspot-method.md (weights, statistics, FDR, gi_star_confidence '
    'classes). See the ADRs for formulas, methodology, and limitations.';
