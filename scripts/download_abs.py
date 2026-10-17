#!/usr/bin/env python3
"""Download ABS Census boundary and DataPack source files into data/raw/.

Fetches each file in SOURCES into data/raw/<category>/<year>/, unzips it,
and records it in data/sources.csv. Safe to re-run: already-downloaded
files and already-extracted folders are skipped unless --force is passed.
"""

import argparse
import csv
import datetime
import hashlib
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SOURCES_CSV = DATA_DIR / "sources.csv"
MANIFEST_FIELDS = ["url", "filename", "download_date", "file_size_bytes", "sha256"]

USER_AGENT = "abs-census-pipeline/1.0"
TIMEOUT = 60
CHUNK_SIZE = 1024 * 1024
MAX_RETRIES = 3

SOURCES = [
    # --- boundaries: 2021, ASGS Edition 3, GDA2020 ---
    {
        "category": "boundaries", "year": 2021, "geography": "SA2_STE",
        "filename": "ASGS_2021_MAIN_STRUCTURE_GPKG_GDA2020.zip",
        "url": "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files/ASGS_2021_MAIN_STRUCTURE_GPKG_GDA2020.zip",
    },
    {
        "category": "boundaries", "year": 2021, "geography": "LGA",
        "filename": "LGA_2021_AUST_GDA2020_SHP.zip",
        "url": "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files/LGA_2021_AUST_GDA2020_SHP.zip",
    },
    # --- boundaries: 2016, ASGS 2016 edition, GDA94 ---
    {
        "category": "boundaries", "year": 2016, "geography": "SA2_STE",
        "filename": "1270055001_ASGS_2016_vol_1_geopackage.zip",
        "url": "https://www.abs.gov.au/AUSSTATS/subscriber.nsf/log?openagent&1270055001_ASGS_2016_vol_1_geopackage.zip&1270.0.55.001&Data Cubes&C406A18CE1A6A50ACA257FED00145B1D&0&July 2016&12.07.2016&Latest",
    },
    {
        "category": "boundaries", "year": 2016, "geography": "LGA",
        "filename": "1270055003_lga_2016_aust_shape.zip",
        "url": "https://www.abs.gov.au/AUSSTATS/subscriber.nsf/log?openagent&1270055003_lga_2016_aust_shape.zip&1270.0.55.003&Data Cubes&7951843398FB3F4ECA25833D000EAE34&0&July 2016&07.11.2018&Previous",
    },
    # --- Census GCP DataPacks, short header, 2021 ---
    {
        "category": "datapacks", "year": 2021, "geography": "STE",
        "filename": "2021_GCP_STE_for_AUS_short-header.zip",
        "url": "https://www.abs.gov.au/census/find-census-data/datapacks/download/2021_GCP_STE_for_AUS_short-header.zip",
    },
    {
        "category": "datapacks", "year": 2021, "geography": "SA2",
        "filename": "2021_GCP_SA2_for_AUS_short-header.zip",
        "url": "https://www.abs.gov.au/census/find-census-data/datapacks/download/2021_GCP_SA2_for_AUS_short-header.zip",
    },
    {
        "category": "datapacks", "year": 2021, "geography": "LGA",
        "filename": "2021_GCP_LGA_for_AUS_short-header.zip",
        "url": "https://www.abs.gov.au/census/find-census-data/datapacks/download/2021_GCP_LGA_for_AUS_short-header.zip",
    },
    # --- Census GCP DataPacks, short header, 2016 ---
    {
        "category": "datapacks", "year": 2016, "geography": "STE",
        "filename": "2016_GCP_STE_for_AUS_short-header.zip",
        "url": "https://www.abs.gov.au/census/find-census-data/datapacks/download/2016_GCP_STE_for_AUS_short-header.zip",
    },
    {
        "category": "datapacks", "year": 2016, "geography": "SA2",
        "filename": "2016_GCP_SA2_for_AUS_short-header.zip",
        "url": "https://www.abs.gov.au/census/find-census-data/datapacks/download/2016_GCP_SA2_for_AUS_short-header.zip",
    },
    {
        "category": "datapacks", "year": 2016, "geography": "LGA",
        "filename": "2016_GCP_LGA_for_AUS_short-header.zip",
        "url": "https://www.abs.gov.au/census/find-census-data/datapacks/download/2016_GCP_LGA_for_AUS_short-header.zip",
    },
]


def download(url, dest_path):
    """Stream url to dest_path via a .part temp file, retrying on failure."""
    tmp_path = dest_path.with_name(dest_path.name + ".part")
    headers = {"User-Agent": USER_AGENT}
    encoded_url = quote(url, safe=":/?&=")
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with requests.get(encoded_url, headers=headers, stream=True, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
            tmp_path.rename(dest_path)
            return
        except (requests.RequestException, OSError) as exc:
            last_err = exc
            tmp_path.unlink(missing_ok=True)
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt
                print(f"  download failed ({exc}); retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"failed to download {url} after {MAX_RETRIES} attempts") from last_err


def extract(zip_path, extract_dir, force=False):
    """Unzip zip_path into extract_dir. Returns False if skipped."""
    already = extract_dir.exists() and any(extract_dir.iterdir())
    if already and not force:
        return False
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(extract_dir)
    return True


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def load_existing_manifest_filenames():
    if not SOURCES_CSV.exists():
        return set()
    with open(SOURCES_CSV, newline="", encoding="utf-8") as f:
        return {row["filename"] for row in csv.DictReader(f)}


def append_manifest_row(row):
    file_exists = SOURCES_CSV.exists()
    SOURCES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(SOURCES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def process_source(src, force, manifest_filenames):
    dest_dir = DATA_DIR / "raw" / src["category"] / str(src["year"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / src["filename"]
    extract_dir = dest_dir / dest_path.stem
    label = f"[{src['category']}/{src['year']}/{src['geography']}] {src['filename']}"

    if dest_path.exists() and not force:
        print(f"{label}: already downloaded, skipping download")
    else:
        print(f"{label}: downloading...")
        download(src["url"], dest_path)
        print(f"{label}: download complete")

    if extract(dest_path, extract_dir, force=force):
        print(f"{label}: extracted")
    else:
        print(f"{label}: already extracted, skipping")

    if force or src["filename"] not in manifest_filenames:
        size = dest_path.stat().st_size
        sha256 = sha256_of_file(dest_path)
        append_manifest_row({
            "url": src["url"],
            "filename": src["filename"],
            "download_date": datetime.date.today().isoformat(),
            "file_size_bytes": size,
            "sha256": sha256,
        })
        manifest_filenames.add(src["filename"])


def main():
    parser = argparse.ArgumentParser(description="Download ABS Census boundary and DataPack source files.")
    parser.add_argument("--only", choices=["boundaries", "datapacks"], help="Only process this category.")
    parser.add_argument("--year", type=int, choices=[2016, 2021], help="Only process this year.")
    parser.add_argument("--force", action="store_true", help="Re-download and re-extract even if already present.")
    args = parser.parse_args()

    sources = SOURCES
    if args.only:
        sources = [s for s in sources if s["category"] == args.only]
    if args.year:
        sources = [s for s in sources if s["year"] == args.year]

    if not sources:
        print("No matching sources.", file=sys.stderr)
        return 1

    manifest_filenames = load_existing_manifest_filenames()
    for src in sources:
        process_source(src, args.force, manifest_filenames)
    return 0


if __name__ == "__main__":
    sys.exit(main())
