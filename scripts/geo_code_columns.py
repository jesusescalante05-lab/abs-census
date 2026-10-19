"""Column-name and file/layer lookup tables for ASGS boundary & DataPack sources.

ABS uses different column names for the same concept across vintage (2016 vs
2021) and product (boundary file vs DataPack CSV) -- e.g. boundary files use
STATE_CODE_<year> while DataPacks use STE_CODE_<year> for the same thing.
This file is the single place that mapping lives, keyed by (census_year, geo_level).
"""

YEARS = (2016, 2021)
LEVELS = ("STE", "SA2", "LGA")

BOUNDARY_SRID = {2016: 4283, 2021: 7844}

BOUNDARY_SOURCE = {
    (2016, "STE"): {
        "path": "data/raw/boundaries/2016/1270055001_ASGS_2016_vol_1_geopackage/ASGS 2016 Volume 1.gpkg",
        "layer": "STE_2016_AUST",
    },
    (2016, "SA2"): {
        "path": "data/raw/boundaries/2016/1270055001_ASGS_2016_vol_1_geopackage/ASGS 2016 Volume 1.gpkg",
        "layer": "SA2_2016_AUST",
    },
    (2016, "LGA"): {
        "path": "data/raw/boundaries/2016/1270055003_lga_2016_aust_shape/LGA_2016_AUST.shp",
        "layer": None,
    },
    (2021, "STE"): {
        "path": "data/raw/boundaries/2021/ASGS_2021_MAIN_STRUCTURE_GPKG_GDA2020/ASGS_2021_Main_Structure_GDA2020.gpkg",
        "layer": "STE_2021_AUST_GDA2020",
    },
    (2021, "SA2"): {
        "path": "data/raw/boundaries/2021/ASGS_2021_MAIN_STRUCTURE_GPKG_GDA2020/ASGS_2021_Main_Structure_GDA2020.gpkg",
        "layer": "SA2_2021_AUST_GDA2020",
    },
    (2021, "LGA"): {
        "path": "data/raw/boundaries/2021/LGA_2021_AUST_GDA2020_SHP/LGA_2021_AUST_GDA2020.shp",
        "layer": None,
    },
}

# Geography-code column, per (year, level), as it appears in the BOUNDARY file.
BOUNDARY_CODE_COL = {
    (2016, "STE"): "STATE_CODE_2016",
    (2016, "SA2"): "SA2_MAINCODE_2016",
    (2016, "LGA"): "LGA_CODE16",
    (2021, "STE"): "STATE_CODE_2021",
    (2021, "SA2"): "SA2_CODE_2021",
    (2021, "LGA"): "LGA_CODE21",
}

# Geography-name column, per (year, level), as it appears in the BOUNDARY file.
BOUNDARY_NAME_COL = {
    (2016, "STE"): "STATE_NAME_2016",
    (2016, "SA2"): "SA2_NAME_2016",
    (2016, "LGA"): "LGA_NAME16",
    (2021, "STE"): "STATE_NAME_2021",
    (2021, "SA2"): "SA2_NAME_2021",
    (2021, "LGA"): "LGA_NAME21",
}

# Parent-state code column, per (year, level). Not applicable to STE (the
# region code already IS the state code there).
BOUNDARY_STATE_COL = {
    (2016, "SA2"): "STATE_CODE_2016",
    (2016, "LGA"): "STE_CODE16",
    (2021, "SA2"): "STATE_CODE_2021",
    (2021, "LGA"): "STE_CODE21",
}

# SA2-only parent columns (SA3/SA4/GCCSA). Not present for STE/LGA.
BOUNDARY_PARENT_SA3_COL = {2016: "SA3_CODE_2016", 2021: "SA3_CODE_2021"}
BOUNDARY_PARENT_SA4_COL = {2016: "SA4_CODE_2016", 2021: "SA4_CODE_2021"}
BOUNDARY_PARENT_GCCSA_COL = {2016: "GCCSA_CODE_2016", 2021: "GCCSA_CODE_2021"}

# Area (sq km) column, per (year, level), as it appears in the BOUNDARY file.
BOUNDARY_AREA_COL = {
    (2016, "STE"): "AREA_ALBERS_SQKM",
    (2016, "SA2"): "AREA_ALBERS_SQKM",
    (2016, "LGA"): "AREASQKM16",
    (2021, "STE"): "AREA_ALBERS_SQKM",
    (2021, "SA2"): "AREA_ALBERS_SQKM",
    (2021, "LGA"): "AREASQKM21",
}

# Geography-code column, per (year, level), as it appears in the DATAPACK CSV.
DATAPACK_CODE_COL = {
    (2016, "STE"): "STE_CODE_2016",
    (2016, "SA2"): "SA2_MAINCODE_2016",
    (2016, "LGA"): "LGA_CODE_2016",
    (2021, "STE"): "STE_CODE_2021",
    (2021, "SA2"): "SA2_CODE_2021",
    (2021, "LGA"): "LGA_CODE_2021",
}


def normalize_region_code(raw_code, geo_level):
    """Strip ABS's 'LGA' text prefix from DataPack LGA codes (boundary files
    store the bare code, e.g. '10050'; DataPacks store 'LGA10050')."""
    if geo_level == "LGA" and raw_code.startswith("LGA"):
        return raw_code[len("LGA"):]
    return raw_code
