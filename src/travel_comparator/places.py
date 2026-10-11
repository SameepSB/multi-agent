"""Place lookup and illustrative cost estimation for cities outside the curated data set."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Origins in the curated data set; avoids a network lookup for the common cases.
KNOWN_ORIGIN_COORDINATES: dict[str, tuple[float, float, str]] = {
    "New York": (40.7128, -74.0060, "US"),
    "Los Angeles": (34.0522, -118.2437, "US"),
    "Chicago": (41.8781, -87.6298, "US"),
    "Dallas": (32.7767, -96.7970, "US"),
    "Atlanta": (33.7490, -84.3880, "US"),
}

# Illustrative nightly hotel price in USD by cost tier of the destination country.
HOTEL_TIERS_USD = {"budget": 70, "moderate": 120, "upper": 190, "premium": 260}
DEFAULT_HOTEL_TIER = "moderate"
COUNTRY_TIERS = {
    "budget": "IN ID VN TH PH EG MA TR MX CO PE BR AR ZA KE NP LK KH PK BD UA GE AL MK RS".split(),
    "moderate": "US CA ES PT GR CZ PL HU HR MY CN TW KR CL UY CR PA JP SK EE LV LT CY MT".split(),
    "upper": "GB FR DE IT NL BE AT IE NZ AU AE SG HK IL SA QA KW".split(),
    "premium": "CH NO DK SE IS LU MC BM MV".split(),
}
COUNTRY_TIERS["moderate"] += ["BG", "RO"]
_TIER_BY_COUNTRY = {code: tier for tier, codes in COUNTRY_TIERS.items() for code in codes}

ESTIMATE_SOURCE = "Travel Advisor distance and country cost-tier estimate v1.0.0"


class UnknownPlaceError(ValueError):
    """Raised when a place name cannot be resolved to coordinates."""


@dataclass(frozen=True)
class Place:
    name: str
    latitude: float
    longitude: float
    country_code: str


def distance_km(a: Place | tuple[float, float], b: Place | tuple[float, float]) -> float:
    lat1, lon1 = (a.latitude, a.longitude) if isinstance(a, Place) else a
    lat2, lon2 = (b.latitude, b.longitude) if isinstance(b, Place) else b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = math.radians(lon2 - lon1)
    h = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def estimate_flight_usd(km: float, international: bool) -> int:
    fare = 60 + 0.09 * km
    if international:
        fare += 120
    return round(min(fare, 1800))


def estimate_travel_hours(km: float) -> float:
    return round(1.5 + km / 800, 1)


def estimate_hotel_usd(country_code: str | None) -> int:
    tier = _TIER_BY_COUNTRY.get((country_code or "").upper(), DEFAULT_HOTEL_TIER)
    return HOTEL_TIERS_USD[tier]


class Geocoder:
    """Resolves free-text place names with the keyless Open-Meteo geocoding API."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout
        self._cache: dict[str, Place] = {}

    async def lookup(self, name: str) -> Place:
        key = name.casefold()
        if key in self._cache:
            return self._cache[key]
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=False, trust_env=False
            ) as client:
                response = await client.get(
                    GEOCODING_URL,
                    params={"name": name, "count": 1, "language": "en", "format": "json"},
                )
            response.raise_for_status()
            payload: Any = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError("Place lookup is unavailable.") from exc
        results = payload.get("results") if isinstance(payload, dict) else None
        if not results:
            raise UnknownPlaceError(f"Could not find a place named {name!r}.")
        top = results[0]
        try:
            place = Place(
                name=name,
                latitude=float(top["latitude"]),
                longitude=float(top["longitude"]),
                country_code=str(top.get("country_code", "")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UnknownPlaceError(f"Could not find a place named {name!r}.") from exc
        self._cache[key] = place
        return place
