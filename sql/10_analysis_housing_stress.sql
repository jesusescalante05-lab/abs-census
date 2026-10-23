-- =====================================================================
-- 10_analysis_housing_stress.sql
-- ADR-001: Housing cost burden indicator -- analysis.housing_stress_sa2
-- Run after 00_reset_database.sql and a full load_all.py run.
-- =====================================================================

DROP VIEW IF EXISTS analysis.housing_stress_sa2;

CREATE VIEW analysis.housing_stress_sa2 AS
WITH perth_sa2 AS (
    -- Scope (ADR-001): 2021 SA2s inside Greater Perth.
    SELECT region_code, region_name, geom
    FROM geo.region
    WHERE census_year = 2021 AND geo_level = 'SA2' AND parent_gccsa = '5GPER'
),
raw AS (
    -- Long -> wide pivot: join census.variable and filter on (table_id,
    -- short_code) together -- never a bare variable_code or short_code alone
    -- -- per ADR-001's warning that short codes like 'Total_Total' repeat
    -- across tables.
    SELECT
        v.region_code,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G37' AND cv.short_code = 'Total_Total')        AS households,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G37' AND cv.short_code = 'R_Tot_Total')         AS renting,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G37' AND cv.short_code = 'O_MTG_Total')         AS mortgaged,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G37' AND cv.short_code = 'Ten_type_NS_Total')   AS tenure_not_stated,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G37' AND cv.short_code = 'R_ST_h_auth_Total')   AS social_housing_authority,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G37' AND cv.short_code = 'R_Com_Hp_Total')      AS community_housing,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G02' AND cv.short_code = 'Median_rent_weekly')             AS median_rent_weekly_raw,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G02' AND cv.short_code = 'Median_tot_hhd_inc_weekly')      AS median_income_weekly_raw,
        MAX(v.value) FILTER (WHERE cv.table_id = 'G02' AND cv.short_code = 'Median_mortgage_repay_monthly')  AS median_mortgage_monthly_raw
    FROM census.value v
    JOIN census.variable cv
        ON cv.census_year = v.census_year AND cv.variable_code = v.variable_code
    JOIN perth_sa2 p ON p.region_code = v.region_code
    WHERE v.census_year = 2021 AND v.geo_level = 'SA2'
      AND (cv.table_id, cv.short_code) IN (
          ('G37', 'Total_Total'), ('G37', 'R_Tot_Total'), ('G37', 'O_MTG_Total'),
          ('G37', 'Ten_type_NS_Total'), ('G37', 'R_ST_h_auth_Total'), ('G37', 'R_Com_Hp_Total'),
          ('G02', 'Median_rent_weekly'), ('G02', 'Median_tot_hhd_inc_weekly'), ('G02', 'Median_mortgage_repay_monthly')
      )
    GROUP BY v.region_code
),
scored AS (
    SELECT
        p.region_code, p.region_name, p.geom,
        r.households, r.renting, r.mortgaged,
        r.tenure_not_stated, r.social_housing_authority, r.community_housing,
        NULLIF(r.median_rent_weekly_raw, 0)      AS median_rent_weekly,       -- R1
        NULLIF(r.median_income_weekly_raw, 0)    AS median_income_weekly,     -- R1
        NULLIF(r.median_mortgage_monthly_raw, 0) AS median_mortgage_monthly,  -- R1
        CASE
            WHEN r.households IS NULL OR r.households < 100 THEN 'few_households'
            WHEN r.renting IS NULL OR r.renting < 30        THEN 'few_renters'
            WHEN NULLIF(r.median_rent_weekly_raw, 0) IS NULL
                 OR NULLIF(r.median_income_weekly_raw, 0) IS NULL THEN 'no_median'
            ELSE 'ok'
        END AS rent_status,
        CASE
            WHEN r.households IS NULL OR r.households < 100 THEN 'few_households'
            WHEN r.mortgaged IS NULL OR r.mortgaged < 30     THEN 'few_mortgaged'
            WHEN NULLIF(r.median_mortgage_monthly_raw, 0) IS NULL
                 OR NULLIF(r.median_income_weekly_raw, 0) IS NULL THEN 'no_median'
            ELSE 'ok'
        END AS mortgage_status
    FROM perth_sa2 p
    LEFT JOIN raw r ON r.region_code = p.region_code
)
SELECT
    region_code,
    region_name,
    households,     -- never NULLed: R2 gates the calculated indicators below, not the raw counts
    renting,
    mortgaged,
    rent_status,
    mortgage_status,
    CASE WHEN rent_status = 'ok'
         THEN median_rent_weekly / median_income_weekly
    END AS rent_burden,
    CASE WHEN mortgage_status = 'ok'
         THEN (median_mortgage_monthly * 12 / 52) / median_income_weekly
    END AS mortgage_burden,
    CASE WHEN households >= 100
         THEN renting / NULLIF(households - tenure_not_stated, 0)   -- R2 + R5
    END AS renter_share,
    CASE WHEN households >= 100
         THEN (social_housing_authority + community_housing) / NULLIF(renting, 0)  -- R2 + R5
    END AS social_housing_share,
    geom
FROM scored;

COMMENT ON VIEW analysis.housing_stress_sa2 IS
    'Housing cost burden indicators for Greater Perth SA2s, 2021 Census. '
    'Implements docs/decisions/ADR-001-housing-cost-burden.md (indicators, '
    'rules R1-R6, rent_status/mortgage_status). See the ADR for formulas, '
    'data-quality rules, and limitations.';
