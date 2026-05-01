import logging
from typing import Optional, Tuple

import httpx  # type: ignore

logger = logging.getLogger(__name__)


async def geocode_village_district(village: str, district: str, state: str = "Uttar Pradesh", country: str = "India") -> Optional[Tuple[float, float]]:
    """
    Use Nominatim (OpenStreetMap) to geocode a (village, district, state, country) into (lat, lon).
    """
    if not village or not district:
        return None

    query = f"{village}, {district}, {state}, {country}"
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
    }

    headers = {
        "User-Agent": "Lexi-AI-Land-Assistant/1.0 (contact: support@example.com)",
    }

    logger.info("Geocoding location via Nominatim: %s", query)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if not data:
        logger.warning("No geocoding results for: %s", query)
        return None

    try:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    except (KeyError, ValueError, TypeError) as exc:
        logger.error("Failed to parse geocoding response for %s: %s", query, exc)
        return None

