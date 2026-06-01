#!/usr/bin/env python3
"""Build drive-time isochrones for the Bell County Expo Center as GeoJSON.

Calls the OpenRouteService (ORS) isochrones API once for a fixed origin and
writes nested drive-time bands (10/20/30/40/60 min by default) to a static
GeoJSON file that the Leaflet page in `docs/` renders. ORS is contacted at
*build* time only; the published map needs no key.

If ORS_API_KEY is not set, falls back to approximate concentric-circle bands
(average driving speed x time) that are clearly labelled "approximate", so the
page always renders. Rerun with a key to replace them with real road-network
isochrones.

Configured entirely via environment variables; see README.md.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone

import requests

# --- Configuration (env) ----------------------------------------------------

ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
# Origin defaults to the Bell County Expo Center / Cadence Bank Arena.
ARENA_LAT = float(os.environ.get("ARENA_LAT", "31.0305"))
ARENA_LON = float(os.environ.get("ARENA_LON", "-97.4787"))
# Comma-separated seconds; ascending. ORS free-tier driving-car max is 3600s.
RANGES = os.environ.get("RANGES", "600,1200,1800,2400,3600")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "docs/isochrones.geojson")
# If truthy, resolve the origin by geocoding the address instead of lat/lon.
GEOCODE = os.environ.get("GEOCODE", "").lower() in ("1", "true", "yes")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

ORS_ISO_URL = "https://api.openrouteservice.org/v2/isochrones/driving-car"
ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ARENA_NAME = "Bell County Expo Center / Cadence Bank Arena"
ARENA_ADDRESS = "301 W Loop 121, Belton, TX 76513"
# Average mixed urban/highway speed used only for the no-key fallback.
FALLBACK_SPEED_MPH = 35.0

# minutes -> fill color (ColorBrewer diverging ramp; closer = cooler/blue).
BAND_COLORS = {
    10: "#2c7bb6",
    20: "#abd9e9",
    30: "#ffffbf",
    40: "#fdae61",
    60: "#d7191c",
}
DEFAULT_COLOR = "#888888"


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    log(f"ERROR: {msg}")
    sys.exit(1)


def color_for(minutes: int) -> str:
    return BAND_COLORS.get(minutes, DEFAULT_COLOR)


# --- Inputs ------------------------------------------------------------------

def parse_ranges() -> list[int]:
    try:
        ranges = sorted({int(x.strip()) for x in RANGES.split(",") if x.strip()})
    except ValueError:
        fail(f"RANGES must be comma-separated integers (got {RANGES!r}).")
    if not ranges:
        fail("RANGES is empty.")
    if max(ranges) > 3600:
        log("WARNING: a range exceeds 3600s; ORS free-tier driving-car may reject it.")
    return ranges


def resolve_origin() -> tuple[float, float]:
    """Return the origin as (lon, lat) in GeoJSON/ORS order."""
    if GEOCODE and ORS_API_KEY:
        try:
            resp = requests.get(
                ORS_GEOCODE_URL,
                params={"api_key": ORS_API_KEY, "text": ARENA_ADDRESS, "size": 1},
                timeout=30,
            )
            if resp.status_code == 200:
                feats = resp.json().get("features", [])
                if feats:
                    lon, lat = feats[0]["geometry"]["coordinates"][:2]
                    log(f"Geocoded {ARENA_ADDRESS!r} -> lon={lon} lat={lat}")
                    return float(lon), float(lat)
            log(f"WARNING: geocode failed ({resp.status_code}); using configured lat/lon.")
        except Exception as exc:  # noqa: BLE001 - geocoding is best-effort
            log(f"WARNING: geocode error ({exc}); using configured lat/lon.")
    return ARENA_LON, ARENA_LAT


# --- OpenRouteService --------------------------------------------------------

def fetch_ors_isochrones(origin: tuple[float, float], ranges: list[int]) -> dict:
    headers = {
        "Authorization": ORS_API_KEY,  # ORS uses the raw key, no "Bearer" prefix.
        "Content-Type": "application/json",
        "Accept": "application/json, application/geo+json",
    }
    body = {
        "locations": [list(origin)],  # [lon, lat]
        "range": ranges,
        "range_type": "time",
        "smoothing": 25,
    }
    resp = requests.post(ORS_ISO_URL, headers=headers, json=body, timeout=60)
    if resp.status_code != 200:
        fail(f"ORS isochrones failed ({resp.status_code}): {resp.text}")
    return resp.json()


# --- GeoJSON assembly --------------------------------------------------------

def base_properties(origin: tuple[float, float], approximate: bool, source: str) -> dict:
    return {
        "name": ARENA_NAME,
        "address": ARENA_ADDRESS,
        "origin": list(origin),
        "source": source,
        "approximate": approximate,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def annotate(feature: dict, minutes: int, approximate: bool) -> dict:
    label = f"~{minutes} min (approx)" if approximate else f"{minutes} min"
    feature.setdefault("properties", {})
    feature["properties"].update(
        {"minutes": minutes, "label": label, "color": color_for(minutes)}
    )
    return feature


def normalize_features(geojson: dict, ranges: list[int], origin: tuple[float, float]) -> dict:
    feats = sorted(geojson.get("features", []), key=lambda f: f["properties"]["value"])
    for feat in feats:
        annotate(feat, int(round(feat["properties"]["value"] / 60)), approximate=False)
    return {
        "type": "FeatureCollection",
        "properties": base_properties(origin, approximate=False, source="openrouteservice"),
        "features": feats,
    }


def build_fallback_circles(origin: tuple[float, float], ranges: list[int]) -> dict:
    lon, lat = origin
    miles_per_deg_lat = 69.0
    miles_per_deg_lon = 69.172 * math.cos(math.radians(lat))
    feats = []
    for seconds in ranges:
        minutes = int(round(seconds / 60))
        radius_miles = FALLBACK_SPEED_MPH * (seconds / 3600.0)
        dlat = radius_miles / miles_per_deg_lat
        dlon = radius_miles / miles_per_deg_lon
        ring = []
        for i in range(65):  # 64 segments, closed ring
            theta = 2 * math.pi * i / 64
            ring.append([lon + dlon * math.cos(theta), lat + dlat * math.sin(theta)])
        feats.append(
            annotate(
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}},
                minutes,
                approximate=True,
            )
        )
    return {
        "type": "FeatureCollection",
        "properties": base_properties(origin, approximate=True, source="approximate-circles"),
        "features": feats,
    }


def write_geojson(path: str, geojson: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


# --- Main --------------------------------------------------------------------

def main() -> None:
    ranges = parse_ranges()
    origin = resolve_origin()
    log(f"Origin (lon, lat): {origin}; ranges (s): {ranges}")

    if ORS_API_KEY:
        log("Mode: openrouteservice (real isochrones).")
        geojson = normalize_features(fetch_ors_isochrones(origin, ranges), ranges, origin)
    else:
        log("WARNING: ORS_API_KEY not set; building APPROXIMATE circle bands.")
        log(f"         (avg {FALLBACK_SPEED_MPH:g} mph; rerun with a key for real drive times.)")
        geojson = build_fallback_circles(origin, ranges)

    summary = (
        f"features={len(geojson['features'])} "
        f"approximate={geojson['properties']['approximate']} "
        f"source={geojson['properties']['source']}"
    )
    if DRY_RUN:
        log(f"[dry-run] would write {OUTPUT_PATH}: {summary}")
        return

    write_geojson(OUTPUT_PATH, geojson)
    log(f"Wrote {OUTPUT_PATH}: {summary}")


if __name__ == "__main__":
    main()
