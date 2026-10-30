-- =====================================================================
-- 01_geo_mesh_block.sql
-- 2021 ABS Mesh Block boundaries (Greater Perth only), for the ADR-003
-- cartographic display mask. Non-destructive: CREATE TABLE/INDEX IF NOT
-- EXISTS -- safe to run on an already-populated database.
--
-- Build order: 00_reset_database.sql -> 01_geo_mesh_block.sql -> loaders
-- (load_boundaries.py, load_mesh_blocks.py, ...) -> 10_... -> 11_... -> 12_...
-- See docs/TECHNICAL_REFERENCE.md.
-- =====================================================================

CREATE TABLE IF NOT EXISTS geo.mesh_block (
    census_year  smallint NOT NULL REFERENCES ref.census_year (census_year),
    mb_code      text NOT NULL,
    mb_category  text NOT NULL,
    sa2_code     text NOT NULL,
    sa2_level    text GENERATED ALWAYS AS ('SA2') STORED,
    area_sqkm    double precision,
    geom         geometry(MultiPolygon, 7844),

    PRIMARY KEY (census_year, mb_code),
    FOREIGN KEY (census_year, sa2_level, sa2_code)
        REFERENCES geo.region (census_year, geo_level, region_code)
);

CREATE INDEX IF NOT EXISTS mesh_block_geom_gix ON geo.mesh_block USING gist (geom);
CREATE INDEX IF NOT EXISTS mesh_block_sa2_idx ON geo.mesh_block (census_year, sa2_code);
