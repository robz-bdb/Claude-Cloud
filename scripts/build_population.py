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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

# --- Configuration (env) ----------------------------------------------------

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")
# Comma-separated real census years. 2010/2020 are decennial 100% counts;
# others are ACS 5-year estimates (e.g. 2015, 2023). Data model is per-year so
# more years extend cleanly.
YEARS = os.environ.get("YEARS", "2010,2015,2020,2023")
# A current-year estimate that real census products lag: each base-year (2020)
# block group is scaled by its county's base->current Census PEP growth factor,
# then interpolated like any other year. Set CURRENT_YEAR="" to disable.
CURRENT_YEAR = os.environ.get("CURRENT_YEAR", "2024")
CURRENT_BASE_YEAR = int(os.environ.get("CURRENT_BASE_YEAR", "2020"))
PEP_VINTAGE = os.environ.get("PEP_VINTAGE", "2024")
ISOCHRONES_PATH = os.environ.get("ISOCHRONES_PATH", "docs/isochrones.geojson")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "docs/population.json")
# Texas; the 60-min reach around Belton stays within the state.
STATE_FIPS = os.environ.get("STATE_FIPS", "48")
# Block-group population is fetched one county at a time (~254 in TX); fetch them
# concurrently to keep the build to a couple of minutes.
CENSUS_WORKERS = int(os.environ.get("CENSUS_WORKERS", "16"))
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
    """GET a Census API endpoint, returning its 2D array (header + rows).

    The Census API often signals problems (notably an invalid or not-yet-
    activated key) with an HTTP 200 and a plain-text body rather than an error
    status, so a bare resp.json() would fail opaquely. Surface the body instead.
    """
    safe = {k: v for k, v in params.items() if k != "key"}
    resp = requests.get(url, params=params, timeout=60)
    body = resp.text.strip()
    if resp.status_code != 200:
        fail(f"Census request failed ({resp.status_code}) for {url} {safe}\n{body[:300]}")
    try:
        return resp.json()
    except ValueError:
        hint = ""
        if "valid key" in body.lower() or "not valid" in body.lower():
            hint = (
                "\nThe CENSUS_API_KEY appears invalid or not yet activated. Check the "
                "secret value, and click the activation link Census emailed you."
            )
        fail(f"Census returned non-JSON (200) for {url} {safe}\n{body[:300]}{hint}")


def fetch_counties(year: int, dataset: str) -> list[str]:
    """Return every county FIPS (3-digit, zero-padded) in the state for a year."""
    rows = census_get(
        f"{CENSUS_BASE}/{year}/{dataset}",
        {"get": "NAME", "for": "county:*", "in": f"state:{STATE_FIPS}", "key": CENSUS_API_KEY},
    )
    header = rows[0]
    ci = header.index("county")
    return sorted({r[ci] for r in rows[1:]})


def _fetch_county_bg(year: int, dataset: str, var: str, county: str) -> dict:
    """Return {GEOID(12): population} for one county's block groups."""
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
    out: dict[str, int] = {}
    for r in rows[1:]:
        geoid = r[idx["state"]] + r[idx["county"]] + r[idx["tract"]] + r[idx["block group"]]
        try:
            val = int(r[vi])
        except (TypeError, ValueError):
            val = 0
        # ACS uses large negative sentinels for suppressed estimates.
        out[geoid] = max(val, 0)
    return out


def fetch_block_group_pop(year: int, cfg: dict) -> dict:
    """Return {GEOID(12): population} for every block group in the state.

    Block-group queries must be scoped to one state, and the county wildcard is
    not reliably supported across all vintages, so iterate counties explicitly,
    fetching them concurrently.
    """
    dataset, var = cfg["dataset"], cfg["var"]
    counties = fetch_counties(year, dataset)
    log(f"  {year}: {dataset} {var} over {len(counties)} counties in state {STATE_FIPS}")
    pops: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=CENSUS_WORKERS) as pool:
        for county_pops in pool.map(
            lambda c: _fetch_county_bg(year, dataset, var, c), counties
        ):
            pops.update(county_pops)
    log(f"  {year}: {len(pops)} block groups, total state pop {sum(pops.values()):,}")
    return pops


# --- Population Estimates Program (current-year growth) -----------------------

def fetch_pep_factors(base_year: int, current_year: int, vintage: str) -> dict:
    """Return {county FIPS(3): base->current growth factor} from Census PEP.

    The decennial/ACS products lag the present; PEP publishes point-in-time
    July-1 county estimates each year. We use the per-county base->current ratio
    to age the base-year block groups forward (uniform growth within a county).

    The Census *API* does not expose recent PEP vintages, but the county totals
    are published as a flat CSV on the FTP server (same host as the TIGER
    geometry), so we read that. Override with PEP_CSV_URL if the path changes.
    """
    import csv
    import io

    url = os.environ.get("PEP_CSV_URL") or (
        f"https://www2.census.gov/programs-surveys/popest/datasets/"
        f"{base_year}-{vintage}/counties/totals/co-est{vintage}-alldata.csv"
    )
    log(f"  PEP totals CSV: {url}")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        fail(f"PEP CSV download failed ({resp.status_code}): {url}")
    reader = csv.DictReader(io.StringIO(resp.content.decode("latin-1")))
    bcol, ccol = f"POPESTIMATE{base_year}", f"POPESTIMATE{current_year}"
    if reader.fieldnames is None or bcol not in reader.fieldnames or ccol not in reader.fieldnames:
        fail(f"PEP CSV missing {bcol}/{ccol}; columns: {reader.fieldnames}")
    factors: dict[str, float] = {}
    for row in reader:
        if row.get("STATE") != STATE_FIPS or row.get("SUMLEV") != "050":
            continue  # county rows in the target state only
        try:
            base, cur = float(row[bcol]), float(row[ccol])
        except (TypeError, ValueError):
            continue
        if base > 0 and row.get("COUNTY"):
            factors[row["COUNTY"]] = cur / base
    if not factors:
        fail(f"PEP CSV had no usable county rows for state {STATE_FIPS}: {url}")
    log(f"  PEP v{vintage}: {len(factors)} county factors, base {base_year} -> {current_year}")
    return factors


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
    bands = bands.to_crs(EQUAL_AREA_CRS).copy()
    bands["geometry"] = bands.geometry.buffer(0)  # repair self-intersecting polygons
    widest = bands.loc[bands["minutes"].idxmax(), "geometry"]

    # Bounding-box prefilter (via spatial index) then a precise intersects, so we
    # only repair and intersect the BGs that can reach the widest band.
    bgs = bgs_with_pop.to_crs(EQUAL_AREA_CRS)
    hits = bgs.sindex.query(widest, predicate="intersects")
    bgs = bgs.iloc[hits].copy()
    bgs["geometry"] = bgs.geometry.buffer(0)
    bgs = bgs[bgs.intersects(widest)]
    bgs["bg_area"] = bgs.geometry.area

    # Bands are nested, so a vectorized intersection against each band gives
    # cumulative population directly (people reachable within X minutes).
    result: dict[int, int] = {}
    for _, band in bands.iterrows():
        inter_area = bgs.geometry.intersection(band.geometry).area
        frac = (inter_area / bgs["bg_area"]).clip(0, 1)
        result[int(band["minutes"])] = int(round((bgs["pop"] * frac).sum()))
    return result


# --- Output -------------------------------------------------------------------

def growth_pct(pops: dict, order: list[int]):
    first, last = pops.get(str(order[0])), pops.get(str(order[-1]))
    if not first:  # missing or zero -> undefined growth
        return None
    return round((last - first) / first * 100, 1)


def column_label(year: int, current_year: int | None) -> str:
    """Human-honest column header. ACS 5-year estimates are a rolling average
    (~midpoint), not a point-in-time year, and the PEP-scaled column is flagged
    as a current-year estimate so neither is misread as a clean census count."""
    if current_year is not None and year == current_year:
        return f"{year} (current)"
    if year_config(year)["dataset"] == "acs/acs5":
        return f"{year - 4}–{str(year)[-2:]} ACS (~{year - 2})"
    return str(year)  # decennial 100% count


def build_output(
    meta: list[dict], pops_by_year: dict, census_years: list[int],
    current_year: int | None, pep_vintage: str,
) -> dict:
    order = sorted(pops_by_year)  # census years plus the current-year column
    has_current = current_year is not None and current_year in pops_by_year
    columns = [{"key": str(y), "label": column_label(y, current_year)} for y in order]

    bands = []
    for m in meta:
        minutes = m["minutes"]
        population = {str(y): pops_by_year[y][minutes] for y in order}
        bands.append(
            {
                "minutes": minutes,
                "color": m["color"],
                "label": m["label"],
                "population": population,
                "growth_pct": growth_pct(population, order),
            }
        )

    datasets = ", ".join(f"{y}:{year_config(y)['dataset']}" for y in census_years)
    source = f"US Census Bureau ({datasets})"
    method = (
        "Areal interpolation of block-group population into nested drive-time "
        "bands (EPSG:5070, area-weighted); cumulative within each band."
    )
    if has_current:
        source += f" + PEP Vintage {pep_vintage} (county-scaled current year)"
        method += (
            f" The {current_year} (current) column ages each {CURRENT_BASE_YEAR} block "
            f"group by its county's {CURRENT_BASE_YEAR}–{current_year} Census PEP "
            "growth factor (uniform within county), since decennial/ACS products lag "
            "the present."
        )
    source += " + TIGER cartographic boundaries"

    return {
        "name": ARENA_NAME,
        "address": ARENA_ADDRESS,
        "source": source,
        "method": method,
        "years": order,
        "columns": columns,
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

    current_year = int(CURRENT_YEAR) if CURRENT_YEAR.strip() else None

    geo_cache: dict[int, object] = {}
    pops_by_year: dict[int, dict] = {}
    base_bgs = None  # block groups (with pop) for the current-year scaling base
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
        if year == CURRENT_BASE_YEAR:
            base_bgs = bgs
        log(f"  {year} per-band cumulative: " + ", ".join(f"{k}min={v:,}" for k, v in sorted(band_pops.items())))

    # Current-year column: age the base-year block groups by per-county PEP growth.
    if current_year is not None:
        if base_bgs is None:
            fail(f"CURRENT_YEAR={current_year} needs base year {CURRENT_BASE_YEAR} in YEARS={years}.")
        log(f"Current year {current_year} (PEP v{PEP_VINTAGE}, scaled from {CURRENT_BASE_YEAR}):")
        factors = fetch_pep_factors(CURRENT_BASE_YEAR, current_year, PEP_VINTAGE)
        for fips, nm in (("027", "Bell"), ("491", "Williamson"), ("453", "Travis"), ("309", "McLennan")):
            if fips in factors:
                log(f"    {nm} county 2020->{current_year} factor: {factors[fips]:.3f}")
        scaled = base_bgs.copy()
        county_factor = scaled["GEOID"].str[2:5].map(factors).fillna(1.0)
        scaled["pop"] = (scaled["pop"] * county_factor).round().astype(int)
        band_pops = population_in_bands(bands, scaled)
        pops_by_year[current_year] = band_pops
        log(f"  {current_year} per-band cumulative: " + ", ".join(f"{k}min={v:,}" for k, v in sorted(band_pops.items())))

    out = build_output(meta, pops_by_year, years, current_year, PEP_VINTAGE)
    summary = f"years={years} bands={len(out['bands'])}"
    if DRY_RUN:
        log(f"[dry-run] would write {OUTPUT_PATH}: {summary}")
        return

    write_json(OUTPUT_PATH, out)
    log(f"Wrote {OUTPUT_PATH}: {summary}")


if __name__ == "__main__":
    main()
