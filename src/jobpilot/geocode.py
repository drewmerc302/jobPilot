import logging

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
