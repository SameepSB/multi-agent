"""Live flight and hotel prices from SerpApi's Google Flights and Google Hotels engines."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

import httpx

SERPAPI_URL = "https://serpapi.com/search.json"
SOURCE = "SerpApi Google Flights + Hotels"
CACHE_TTL_SECONDS = 900

AIRPORT_CODES = {
    "new york": "JFK",
    "los angeles": "LAX",
    "chicago": "ORD",
    "dallas": "DFW",
    "atlanta": "ATL",
    "austin": "AUS",
    "denver": "DEN",
    "miami": "MIA",
    "san francisco": "SFO",
    "nashville": "BNA",
    "seattle": "SEA",
    "phoenix": "PHX",
    "new orleans": "MSY",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "bengaluru": "BLR",
    "bangalore": "BLR",
    "chennai": "MAA",
    "kolkata": "CCU",
    "hyderabad": "HYD",
    "pune": "PNQ",
    "goa": "GOI",
    "jaipur": "JAI",
    "kochi": "COK",
    "ahmedabad": "AMD",
    "london": "LHR",
    "paris": "CDG",
    "dubai": "DXB",
    "singapore": "SIN",
    "bangkok": "BKK",
    "tokyo": "HND",
    "sydney": "SYD",
    "toronto": "YYZ",
    "frankfurt": "FRA",
    "amsterdam": "AMS",
    "hong kong": "HKG",
}


class LiveProviderError(Exception):
    """Raised when live prices cannot be obtained; callers fall back explicitly."""


@dataclass(frozen=True)
class LiveQuote:
    flight_usd_minor: int
    hotel_per_night_usd_minor: int
    travel_time_hours: float
    observed_at: str


def airport_code(place: str) -> str | None:
    stripped = place.strip()
    if len(stripped) == 3 and stripped.isalpha() and stripped.isupper():
        return stripped
    return AIRPORT_CODES.get(stripped.casefold())


class SerpApiTravelProvider:
    def __init__(
        self,
        api_key: str,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client = client
        self._cache: dict[tuple[str, str, date, int], tuple[float, LiveQuote]] = {}

    async def quote(self, origin: str, destination: str, departure: date, nights: int) -> LiveQuote:
        origin_code, destination_code = airport_code(origin), airport_code(destination)
        if origin_code is None or destination_code is None:
            raise LiveProviderError("airport code unknown")
        key = (origin_code, destination_code, departure, nights)
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        returning = departure + timedelta(days=nights)
        flights = await self._get(
            {
                "engine": "google_flights",
                "departure_id": origin_code,
                "arrival_id": destination_code,
                "outbound_date": departure.isoformat(),
                "return_date": returning.isoformat(),
                "type": "1",
                "currency": "USD",
                "hl": "en",
            }
        )
        hotels = await self._get(
            {
                "engine": "google_hotels",
                "q": f"hotels in {destination}",
                "check_in_date": departure.isoformat(),
                "check_out_date": returning.isoformat(),
                "currency": "USD",
                "hl": "en",
            }
        )
        flight_usd, hours = _cheapest_flight(flights)
        quote = LiveQuote(
            flight_usd_minor=round(flight_usd * 100),
            hotel_per_night_usd_minor=round(_typical_hotel_rate(hotels) * 100),
            travel_time_hours=hours,
            observed_at=datetime.now(UTC).isoformat(),
        )
        self._cache[key] = (time.monotonic(), quote)
        return quote

    async def _get(self, params: dict[str, str]) -> dict[str, Any]:
        query = {**params, "api_key": self._api_key}
        try:
            if self._client is not None:
                response = await self._client.get(SERPAPI_URL, params=query)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(SERPAPI_URL, params=query)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never include the request URL: it carries the API key.
            raise LiveProviderError(type(exc).__name__) from None
        if not isinstance(body, dict) or body.get("error"):
            raise LiveProviderError("provider returned an error")
        return body


def _cheapest_flight(body: dict[str, Any]) -> tuple[float, float]:
    offers = [
        offer
        for offer in [*body.get("best_flights", []), *body.get("other_flights", [])]
        if isinstance(offer.get("price"), int | float) and offer["price"] > 0
    ]
    if not offers:
        raise LiveProviderError("no flight offers")
    best = min(offers, key=lambda offer: offer["price"])
    minutes = best.get("total_duration") or 0
    return float(best["price"]), round(minutes / 60, 1)


def _typical_hotel_rate(body: dict[str, Any]) -> float:
    rates = []
    for prop in body.get("properties", []):
        rate = (prop.get("rate_per_night") or {}).get("extracted_lowest")
        if isinstance(rate, int | float) and rate > 0:
            rates.append(float(rate))
    if not rates:
        raise LiveProviderError("no hotel rates")
    return float(median(rates))
