from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from travel_comparator.providers.nws.client import WeatherProvider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("temperature", "headline", "expected_status"),
    [
        (75, None, "GO"),
        (98, None, "CAUTION"),
        (75, "Hurricane Warning", "NO_GO"),
    ],
)
async def test_live_weather_maps_forecast_and_alerts(
    monkeypatch, temperature, headline, expected_status
):
    data_path = Path(__file__).resolve().parents[2] / "data" / "travel_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    provider = WeatherProvider(False, data, "Travel Comparator (ops@example.com)")

    async def mocked_get(_client, url):
        if "/points/" in url:
            return {
                "properties": {"forecast": "https://api.weather.gov/gridpoints/BOU/1,1/forecast"}
            }
        if "/forecast" in url:
            return {
                "properties": {
                    "periods": [
                        {
                            "isDaytime": True,
                            "temperature": temperature,
                            "shortForecast": "Fixture forecast",
                            "startTime": "2027-03-05T06:00:00-07:00",
                            "endTime": "2027-03-05T18:00:00-07:00",
                        }
                    ]
                }
            }
        return {"features": [] if headline is None else [{"properties": {"headline": headline}}]}

    monkeypatch.setattr(WeatherProvider, "_get", staticmethod(mocked_get))

    result = await provider.assess("Denver", date(2027, 3, 5))

    assert result["status"] == expected_status
    assert result["source"] == "National Weather Service"
    assert result["observed_at"]
    assert (headline or "") in " ".join(result["active_alerts"])


@pytest.mark.asyncio
async def test_live_weather_returns_unavailable_when_requested_date_is_not_forecast(
    monkeypatch,
):
    data_path = Path(__file__).resolve().parents[2] / "data" / "travel_data.json"
    provider = WeatherProvider(
        False,
        json.loads(data_path.read_text(encoding="utf-8")),
        "Travel Comparator (ops@example.com)",
    )

    async def mocked_get(_client, url):
        if "/points/" in url:
            return {
                "properties": {"forecast": "https://api.weather.gov/gridpoints/BOU/1,1/forecast"}
            }
        if "/forecast" in url:
            return {
                "properties": {
                    "periods": [
                        {
                            "isDaytime": True,
                            "temperature": 75,
                            "shortForecast": "Fixture forecast",
                            "startTime": "2027-03-05T06:00:00-07:00",
                            "endTime": "2027-03-05T18:00:00-07:00",
                        }
                    ]
                }
            }
        return {"features": []}

    monkeypatch.setattr(WeatherProvider, "_get", staticmethod(mocked_get))

    result = await provider.assess("Denver", date(2027, 3, 12))

    assert result["status"] == "UNAVAILABLE"
    assert result["high_celsius"] is None
