#!/usr/bin/env python3
"""Estimate population within each drive-time band, across real census years.

Reads the drive-time bands written by `build_isochrones.py`
(`docs/isochrones.geojson`) and, for each configured US Census year, computes how
many people live inside each band by areal interpolation of block-group
population. Writes `docs/population.json`, a static artifact that the Leaflet page
in `docs/` renders as a bands x years summary table. The Census API and TIGER
geometry are contacted at *build* time only; the published map needs no key.

Bands are nested full polygons (10 min is inside 20 min, etc.), so each band's
population is reported cumulatively: people who can reach the arena within X
minutes. Each census year is attributed independently to the same fixed bands, so
the table shows real population growth over time, not modeling/projection.

A CENSUS_API_KEY is required: there is no meaningful offline fallback for real
census counts, and the per-county fan-out would hit rate limits without a key.
Get a free key at https://api.census.gov/data/key_signup.html.

Configured entirely via environment variables; see README.md.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

import requests

# --- Configuration (env) ----------------------------------------------------

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")
# Comma-separated real census years. 2010/2020 are decennial 100% counts;
# others are ACS 5-year estimates (e.g. 2015, 2023). Data model is per-year so
# more years extend cleanly.
YEARS = os.environ.get("YEARS", "2010,2015,2020,2023")
ISOCHRONES_PATH = os.environ.get("ISOCHRONES_PATH", "docs/isochrones.geojson")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "docs/population.json")
# Texas; the 60-min reach around Belton stays within the state.
STATE_FIPS = os.environ.get("STATE_FIPS", "48")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

CENSUS_BASE = "https://api.census.gov/data"
TIGER_BASE = "https://www2.census.gov/geo/tiger"
ARENA_NAME = "Bell County Expo Center / Cadence Bank Arena"
ARENA_ADDRESS = "301 W Loop 121, Belton, TX 76513"
# CONUS Albers equal-area; area ratios are only valid in an equal-area CRS.
EQUAL_AREA_CRS = "EPSG:5070"


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    log(f"ERROR: {msg}")
    sys.exit(1)


# --- Inputs ------------------------------------------------------------------

def parse_years() -> list[int]:
    try:
        years = sorted({int(x.strip()) for x in YEARS.split(",") if x.strip()})
    except ValueError:
        fail(f"YEARS must be comma-separated integers (got {YEARS!r}).")
    if not years:
        fail("YEARS is empty.")
    return years


def year_config(year: int) -> dict:
    """Map a census year to its API dataset, population variable, and the
    cartographic-boundary geometry vintage to attribute it against."""
    if year == 2010:  # decennial SF1, 100% count
        return {"dataset": "dec/sf1", "var": "P001001", "geo_year": 2010}
    if year == 2020:  # decennial DHC, 100% count
        return {"dataset": "dec/dhc", "var": "P1_001N", "geo_year": 2020}
    if year >= 2009:  # ACS 5-year estimate
        return {"dataset": "acs/acs5", "var": "B01003_001E", "geo_year": year}
    fail(f"No Census dataset mapping for year {year}.")


def load_bands(path: str):
    """Load the drive-time bands as a GeoDataFrame in EPSG:4326.

    Returns the GeoDataFrame plus the ordered band metadata (minutes/color/label)
    read straight from the isochrone artifact, so colors never disagree with the
    map.
    """
    import geopandas as gpd  # imported lazily; build-time only dependency
    from shapely.geometry import shape

    if not os.path.exists(path):
        fail(f"{path} not found; run scripts/build_isochrones.py first.")
    with open(path, encoding="utf-8") as fh:
        fc = json.load(fh)
    feats = sorted(fc.get("features", []), key=lambda f: f["properties"]["minutes"])
    if not feats:
        fail(f"{path} has no features.")

    meta = [
        {
            "minutes": int(f["properties"]["minutes"]),
            "color": f["properties"]["color"],
            "label": f["properties"]["label"],
        }
        for f in feats
    ]
    geoms = [shape(f["geometry"]) for f in feats]
    bands = gpd.GeoDataFrame(
        {"minutes": [m["minutes"] for m in meta]},
        geometry=geoms,
        crs="EPSG:4326",
    )
    return bands, meta


# --- Census population --------------------------------------------------------

def census_get(url: str, params: dict) -> list[list]:
    """GET a Census API endpoint, returning its 2D array (header + rows)."""
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        fail(f"Census request failed ({resp.status_code}): {resp.url}\n{resp.text[:300]}")
    return resp.json()


def fetch_counties(year: int, dataset: str) -> list[str]:
    """Return every county FIPS (3-digit, zero-padded) in the state for a year."""
    rows = census_get(
        f"{CENSUS_BASE}/{year}/{dataset}",
        {"get": "NAME", "for": "county:*", "in": f"state:{STATE_FIPS}", "key": CENSUS_API_KEY},
    )
    header = rows[0]
    ci = header.index("county")
    return sorted({r[ci] for r in rows[1:]})


def fetch_block_group_pop(year: int, cfg: dict) -> dict:
    """Return {GEOID(12): population} for every block group in the state.

    Block-group queries must be scoped to one state, and the county wildcard is
    not reliably supported across all vintages, so iterate counties explicitly.
    """
    dataset, var = cfg["dataset"], cfg["var"]
    pops: dict[str, int] = {}
    counties = fetch_counties(year, dataset)
    log(f"  {year}: {dataset} {var} over {len(counties)} counties in state {STATE_FIPS}")
    for county in counties:
        rows = census_get(
            f"{CENSUS_BASE}/{year}/{dataset}",
            {
                "get": var,
                "for": "block group:*",
                "in": f"state:{STATE_FIPS} county:{county}",
                "key": CENSUS_API_KEY,
            },
        )
        header = rows[0]
        vi = header.index(var)
        # Keep FIPS columns as strings; int() would strip leading zeros.
        idx = {k: header.index(k) for k in ("state", "county", "tract", "block group")}
        for r in rows[1:]:
            geoid = r[idx["state"]] + r[idx["county"]] + r[idx["tract"]] + r[idx["block group"]]
            raw = r[vi]
            try:
                val = int(raw)
            except (TypeError, ValueError):
                val = 0
            # ACS uses large negative sentinels for suppressed estimates.
            pops[geoid] = max(val, 0)
    log(f"  {year}: {len(pops)} block groups, total state pop {sum(pops.values()):,}")
    return pops


# --- Block-group geometry -----------------------------------------------------

def bg_shapefile_url(geo_year: int) -> str:
    if geo_year == 2010:
        # 2010 cartographic-boundary files live under a flat dir with the
        # block-group summary level (150) in the name and no /shp/ subdir.
        return f"{TIGER_BASE}/GENZ2010/gz_2010_{STATE_FIPS}_150_00_500k.zip"
    return f"{TIGER_BASE}/GENZ{geo_year}/shp/cb_{geo_year}_{STATE_FIPS}_bg_500k.zip"


def _normalize_geoid(gdf):
    """Return gdf with a clean 12-char string GEOID column, whatever the vintage.

    2020+ CB files carry a tidy `GEOID`; older files put a prefixed value in
    `GEO_ID` (e.g. `1500000US480270208011`) or only the component FIPS columns.
    """
    cols = set(gdf.columns)
    if "GEOID" in cols and gdf["GEOID"].astype(str).str.len().max() == 12:
        gdf["GEOID"] = gdf["GEOID"].astype(str)
    elif "GEO_ID" in cols:
        gdf["GEOID"] = gdf["GEO_ID"].astype(str).str.split("US").str[-1]
    else:
        parts = [c for c in ("STATE", "COUNTY", "TRACT", "BLKGRP") if c in cols]
        if len(parts) != 4:
            fail(f"Cannot derive block-group GEOID from columns: {sorted(cols)}")
        gdf["GEOID"] = (
            gdf["STATE"].astype(str)
            + gdf["COUNTY"].astype(str)
            + gdf["TRACT"].astype(str)
            + gdf["BLKGRP"].astype(str)
        )
    return gdf


def load_block_groups(geo_year: int):
    """Download + read the state's block-group cartographic boundaries.

    Returns a GeoDataFrame with normalized `GEOID` and `geometry` in EPSG:4326.
    """
    import geopandas as gpd

    url = bg_shapefile_url(geo_year)
    log(f"  geometry: {url}")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        fail(f"TIGER geometry download failed ({resp.status_code}): {url}")
    # Download then read via the zip:// virtual path so GDAL picks the .shp.
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(resp.content)
        zip_path = tmp.name
    try:
        gdf = gpd.read_file(f"zip://{zip_path}")
    finally:
        os.unlink(zip_path)
    gdf = _normalize_geoid(gdf)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    return gdf[["GEOID", "geometry"]]


# --- Areal interpolation ------------------------------------------------------

def population_in_bands(bands, bgs_with_pop) -> dict:
    """Cumulative population per band via area-weighted interpolation.

    pop_in_band = sum over BGs of BG_pop * area(BG intersect band) / area(BG),
    computed in an equal-area CRS. Bands are nested, so intersecting each band
    independently yields cumulative population directly.
    """
    import geopandas as gpd

    bands = bands.to_crs(EQUAL_AREA_CRS)
    bgs = bgs_with_pop.to_crs(EQUAL_AREA_CRS)
    # Repair self-intersecting CB / ORS polygons before overlay.
    bands = bands.copy()
    bands["geometry"] = bands.geometry.buffer(0)
    bgs = bgs.copy()
    bgs["geometry"] = bgs.geometry.buffer(0)
    bgs["bg_area"] = bgs.geometry.area

    # Prefilter to BGs touching the widest (max-minutes) band.
    widest = bands.loc[bands["minutes"].idxmax(), "geometry"]
    bgs = bgs[bgs.intersects(widest)]

    result: dict[int, int] = {}
    for _, band in bands.iterrows():
        one = gpd.GeoDataFrame(geometry=[band.geometry], crs=bands.crs)
        inter = gpd.overlay(
            bgs[["GEOID", "pop", "bg_area", "geometry"]],
            one,
            how="intersection",
            keep_geom_type=True,
        )
        if inter.empty:
            result[int(band["minutes"])] = 0
            continue
        frac = (inter.geometry.area / inter["bg_area"]).clip(0, 1)
        result[int(band["minutes"])] = int(round((inter["pop"] * frac).sum()))
    return result


# --- Output -------------------------------------------------------------------

def growth_pct(pops: dict, years: list[int]):
    first, last = pops.get(str(years[0])), pops.get(str(years[-1]))
    if not first:  # missing or zero -> undefined growth
        return None
    return round((last - first) / first * 100, 1)


def build_output(meta: list[dict], pops_by_year: dict, years: list[int]) -> dict:
    datasets = ", ".join(f"{y}:{year_config(y)['dataset']}" for y in years)
    bands = []
    for m in meta:
        minutes = m["minutes"]
        population = {str(y): pops_by_year[y][minutes] for y in years}
        bands.append(
            {
                "minutes": minutes,
                "color": m["color"],
                "label": m["label"],
                "population": population,
                "growth_pct": growth_pct(population, years),
            }
        )
    return {
        "name": ARENA_NAME,
        "address": ARENA_ADDRESS,
        "source": f"US Census Bureau ({datasets}) + TIGER cartographic boundaries",
        "method": (
            "Areal interpolation of block-group population into nested drive-time "
            "bands (EPSG:5070, area-weighted); cumulative within each band."
        ),
        "years": years,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bands": bands,
    }


def write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


# --- Main --------------------------------------------------------------------

def main() -> None:
    if not CENSUS_API_KEY:
        fail(
            "CENSUS_API_KEY is required; no offline fallback for census data. "
            "Get a free key at https://api.census.gov/data/key_signup.html"
        )
    years = parse_years()
    bands, meta = load_bands(ISOCHRONES_PATH)
    log(f"Bands (min): {[m['minutes'] for m in meta]}; years: {years}")

    geo_cache: dict[int, object] = {}
    pops_by_year: dict[int, dict] = {}
    for year in years:
        cfg = year_config(year)
        log(f"Year {year}:")
        pop_by_geoid = fetch_block_group_pop(year, cfg)
        geo_year = cfg["geo_year"]
        if geo_year not in geo_cache:
            geo_cache[geo_year] = load_block_groups(geo_year)
        bgs = geo_cache[geo_year].copy()
        bgs["pop"] = bgs["GEOID"].map(pop_by_geoid).fillna(0).astype(int)
        band_pops = population_in_bands(bands, bgs)
        pops_by_year[year] = band_pops
        log(f"  {year} per-band cumulative: " + ", ".join(f"{k}min={v:,}" for k, v in sorted(band_pops.items())))

    out = build_output(meta, pops_by_year, years)
    summary = f"years={years} bands={len(out['bands'])}"
    if DRY_RUN:
        log(f"[dry-run] would write {OUTPUT_PATH}: {summary}")
        return

    write_json(OUTPUT_PATH, out)
    log(f"Wrote {OUTPUT_PATH}: {summary}")


if __name__ == "__main__":
    main()
