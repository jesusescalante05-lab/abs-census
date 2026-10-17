-- =====================================================================
-- 01_ref_geo.sql
-- ABS Census 2016 + 2021 — reference lists and the geometry table
-- Run while connected to the abs_census database.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Extension and schemas
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS stage;     -- raw imports, exactly as ABS supplies them
CREATE SCHEMA IF NOT EXISTS ref;       -- small lookup lists (allowed values)
CREATE SCHEMA IF NOT EXISTS geo;       -- clean boundaries, one row per region
CREATE SCHEMA IF NOT EXISTS census;    -- numbers + their descriptions (next step)
CREATE SCHEMA IF NOT EXISTS analysis;  -- views and results for QGIS / web

-- ---------------------------------------------------------------------
-- 2. ref.census_year — which census years exist
-- ---------------------------------------------------------------------
CREATE TABLE ref.census_year (
    census_year   smallint PRIMARY KEY,
    asgs_edition  text     NOT NULL,   -- boundary edition used for that census
    source_crs    integer  NOT NULL    -- EPSG code of the files as downloaded
);

INSERT INTO ref.census_year VALUES
    (2016, 'ASGS 2016',           4283),   -- GDA94
    (2021, 'ASGS Edition 3 (2021)', 7844); -- GDA2020

-- ---------------------------------------------------------------------
-- 3. ref.geo_level — which geography levels exist
-- ---------------------------------------------------------------------
CREATE TABLE ref.geo_level (
    geo_level          text     PRIMARY KEY,   -- short code used everywhere
    description        text     NOT NULL,
    is_abs_structure   boolean  NOT NULL,      -- ABS structure vs non-ABS (LGA, POA...)
    sort_order         smallint NOT NULL       -- largest to smallest
);

INSERT INTO ref.geo_level VALUES
    ('STE', 'State and Territory',        true,  1),
    ('LGA', 'Local Government Area',      false, 2),
    ('SA2', 'Statistical Area Level 2',   true,  3);

-- ---------------------------------------------------------------------
-- 4. geo.region — every boundary, every level, every year, in ONE table
-- ---------------------------------------------------------------------
CREATE TABLE geo.region (
    census_year  smallint NOT NULL REFERENCES ref.census_year (census_year),
    geo_level    text     NOT NULL REFERENCES ref.geo_level   (geo_level),
    region_code  text     NOT NULL,   -- text, never integer (see notes)
    region_name  text     NOT NULL,
    state_code   text,                -- handy for filtering, e.g. WA = '5'
    area_sqkm    double precision,    -- as published by the ABS
    geom         geometry(MultiPolygon, 7844),  -- nullable on purpose (see notes)

    PRIMARY KEY (census_year, geo_level, region_code)
);

-- Spatial index: makes "what is inside / near / intersects" queries fast
CREATE INDEX region_geom_gix ON geo.region USING gist (geom);

-- Helps the common filter "one year, one level"
CREATE INDEX region_year_level_idx ON geo.region (census_year, geo_level);

-- ---------------------------------------------------------------------
-- 5. Quick checks — run these after the script finishes
-- ---------------------------------------------------------------------
-- SELECT * FROM ref.census_year;
-- SELECT * FROM ref.geo_level ORDER BY sort_order;
-- SELECT Find_SRID('geo', 'region', 'geom');   -- should return 7844
-- \d geo.region                                 -- psql only: shows keys + indexes
