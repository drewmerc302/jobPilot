import logging
import math

import httpx

from jobpilot.search_params import SearchParams

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def geocode(params: SearchParams) -> None:
    """Resolve params.location to lat/lon via Nominatim if not already set.

    Mutates params.latitude and params.longitude in place.
    No-op if either coordinate is already populated.
    Raises RuntimeError if geocoding fails and no coordinates are available.
    """
    if params.latitude is not None or params.longitude is not None:
        return

    if not params.location:
        return

    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": params.location, "format": "json", "limit": 1},
            headers={"User-Agent": "JobPilot/1.0 (job search app)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
    except Exception as e:
        raise RuntimeError(f"Geocoding '{params.location}' failed: {e}") from e

    if not results:
        raise RuntimeError(f"Nominatim returned no results for '{params.location}'.")

    params.latitude = float(results[0]["lat"])
    params.longitude = float(results[0]["lon"])
    logger.info(
        f"Geocoded '{params.location}' → ({params.latitude:.4f}, {params.longitude:.4f})"
    )


def geocode_point(location_str: str) -> tuple[float, float] | None:
    """Geocode an arbitrary location string, returning (lat, lon) or None on failure."""
    if not location_str or "remote" in location_str.lower():
        return None
    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": location_str, "format": "json", "limit": 1},
            headers={"User-Agent": "JobPilot/1.0 (job search app)"},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        logger.debug(f"Geocoding '{location_str}' failed: {e}")
    return None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
