from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from travel_comparator.providers.serpapi import (
    LiveProviderError,
    SerpApiTravelProvider,
    airport_code,
)


def _provider(handler) -> SerpApiTravelProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SerpApiTravelProvider("test-key", client=client)


def _ok(request: httpx.Request) -> httpx.Response:
    if request.url.params["engine"] == "google_flights":
        return httpx.Response(
            200,
            json={
                "best_flights": [{"price": 450, "total_duration": 600}],
                "other_flights": [{"price": 300, "total_duration": 780}],
            },
        )
    return httpx.Response(
        200,
        json={
            "properties": [
                {"rate_per_night": {"extracted_lowest": 100}},
                {"rate_per_night": {"extracted_lowest": 200}},
                {"rate_per_night": {"extracted_lowest": 300}},
                {"name": "no rate"},
            ]
        },
    )


def test_airport_code_accepts_city_names_and_iata_codes():
    assert airport_code("Delhi") == "DEL"
    assert airport_code("GOI") == "GOI"
    assert airport_code("Nowhereville") is None


def test_quote_uses_cheapest_flight_and_median_hotel():
    provider = _provider(_ok)
    quote = asyncio.run(provider.quote("Delhi", "Goa", date(2027, 1, 10), 4))
    assert quote.flight_usd_minor == 30_000
    assert quote.hotel_per_night_usd_minor == 20_000
    assert quote.travel_time_hours == 13.0


def test_provider_error_hides_api_key():
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "limit"})

    provider = _provider(failing)
    with pytest.raises(LiveProviderError) as caught:
        asyncio.run(provider.quote("Delhi", "Goa", date(2027, 1, 10), 4))
    assert "test-key" not in str(caught.value)


def test_unknown_airport_raises():
    provider = _provider(_ok)
    with pytest.raises(LiveProviderError):
        asyncio.run(provider.quote("Delhi", "Nowhereville", date(2027, 1, 10), 4))
