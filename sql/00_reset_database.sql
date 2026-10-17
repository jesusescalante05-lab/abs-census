-- =====================================================================
-- 00_reset_database.sql
--
-- !! DESTRUCTIVE !! This drops the analysis, census, geo, ref, and stage
-- schemas and ALL data in them, then recreates the ABS Census 2016 + 2021
-- schema from scratch. Do NOT run this against a database you don't
-- intend to fully wipe and rebuild.
--
-- Run while connected to the abs_census database.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Clean slate
-- ---------------------------------------------------------------------
DROP SCHEMA IF EXISTS analysis CASCADE;
DROP SCHEMA IF EXISTS census   CASCADE;
DROP SCHEMA IF EXISTS geo      CASCADE;
DROP SCHEMA IF EXISTS ref      CASCADE;
DROP SCHEMA IF EXISTS stage    CASCADE;

-- ---------------------------------------------------------------------
-- 1. Extension and schemas
-- ---------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA stage;     -- raw imports, exactly as ABS supplies them (tables created by the loader)
CREATE SCHEMA ref;       -- small lookup lists (allowed values)
CREATE SCHEMA geo;       -- clean boundaries, one row per region
CREATE SCHEMA census;    -- numbers + their descriptions
CREATE SCHEMA analysis;  -- views and results for QGIS / web

-- ---------------------------------------------------------------------
-- 2. ref.census_year — which census years exist
-- ---------------------------------------------------------------------
CREATE TABLE ref.census_year (
    census_year   smallint PRIMARY KEY,
    asgs_edition  text     NOT NULL,   -- boundary edition used for that census
    source_crs    integer  NOT NULL    -- EPSG code of the files as downloaded
);

INSERT INTO ref.census_year VALUES
    (2016, 'ASGS 2016',             4283),   -- GDA94
    (2021, 'ASGS Edition 3 (2021)', 7844);   -- GDA2020

-- ---------------------------------------------------------------------
-- 3. ref.geo_level — which geography levels exist
-- ---------------------------------------------------------------------
CREATE TABLE ref.geo_level (
    geo_level         text     PRIMARY KEY,   -- short code used everywhere
    description       text     NOT NULL,
    is_abs_structure  boolean  NOT NULL,      -- ABS structure vs non-ABS (LGA, POA...)
    sort_order        smallint NOT NULL       -- largest to smallest
);

INSERT INTO ref.geo_level VALUES
    ('STE', 'State and Territory',      true,  1),
    ('LGA', 'Local Government Area',    false, 2),
    ('SA2', 'Statistical Area Level 2', true,  3);

-- ---------------------------------------------------------------------
-- 4. geo.region — every boundary, every level, every year, in ONE table
-- ---------------------------------------------------------------------
CREATE TABLE geo.region (
    census_year  smallint NOT NULL REFERENCES ref.census_year (census_year),
    geo_level    text     NOT NULL REFERENCES ref.geo_level   (geo_level),
    region_code  text     NOT NULL,   -- text, never integer (see notes)
    region_name  text     NOT NULL,
    state_code   text,                -- parent state; NULL for STE rows (the code IS the state)
    parent_sa3   text,                -- SA2 rows only, NULL otherwise
    parent_sa4   text,                -- SA2 rows only, NULL otherwise
    parent_gccsa text,                -- SA2 rows only, NULL otherwise
    area_sqkm    double precision,    -- as published by the ABS
    geom         geometry(MultiPolygon, 7844),  -- always 7844; nullable (ABS offshore/no-usual-address categories)

    PRIMARY KEY (census_year, geo_level, region_code)
);

-- Spatial index: makes "what is inside / near / intersects" queries fast
CREATE INDEX region_geom_gix ON geo.region USING gist (geom);

-- Helps the common filter "one year, one level"
CREATE INDEX region_year_level_idx ON geo.region (census_year, geo_level);

-- ---------------------------------------------------------------------
-- 5. census.variable — one row per Census DataPack column, per year
-- ---------------------------------------------------------------------
-- Keyed on ABS's metadata "Sequential" code (e.g. 'G4213') — the only column
-- confirmed 100% unique per year. "Short" (e.g. 'Tot_P_M') repeats across
-- tables, and 38 (2021) / 10 (2016) of those repeats are genuine semantic
-- conflicts (same code, different meaning) — verified against the actual
-- metadata files, not assumed.
CREATE TABLE census.variable (
    census_year      smallint NOT NULL REFERENCES ref.census_year (census_year),
    variable_code    text     NOT NULL,   -- metadata 'Sequential', e.g. 'G4213'
    table_id         text     NOT NULL,   -- metadata 'DataPackfile', e.g. 'G01'
    short_code       text     NOT NULL,   -- metadata 'Short' = the actual DataPack CSV column header
    long_descriptor  text,

    PRIMARY KEY (census_year, variable_code),
    UNIQUE (census_year, table_id, short_code)  -- loader resolves a CSV column -> variable_code via this
);

-- ---------------------------------------------------------------------
-- 6. census.value — one row per (region, variable, year), long/tidy
-- ---------------------------------------------------------------------
CREATE TABLE census.value (
    census_year   smallint NOT NULL,
    geo_level     text     NOT NULL,
    region_code   text     NOT NULL,
    variable_code text     NOT NULL,
    value         numeric,

    PRIMARY KEY (census_year, geo_level, region_code, variable_code),
    FOREIGN KEY (census_year, geo_level, region_code)
        REFERENCES geo.region (census_year, geo_level, region_code),
    FOREIGN KEY (census_year, variable_code)
        REFERENCES census.variable (census_year, variable_code)
);

CREATE INDEX value_year_variable_idx ON census.value (census_year, variable_code);

-- ---------------------------------------------------------------------
-- 7. Quick checks — run these after the script finishes
-- ---------------------------------------------------------------------
-- SELECT * FROM ref.census_year;
-- SELECT * FROM ref.geo_level ORDER BY sort_order;
-- SELECT Find_SRID('geo', 'region', 'geom');   -- should return 7844
-- \d geo.region                                 -- psql only: shows keys + indexes
