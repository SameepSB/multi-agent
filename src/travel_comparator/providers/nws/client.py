from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from travel_comparator.contracts.v1 import WeatherStatus

NWS_ROOT = "https://api.weather.gov"


class RetryableNwsError(RuntimeError):
    retryable = True


class WeatherProvider:
    def __init__(self, stub: bool, data: dict[str, Any], user_agent: str | None = None) -> None:
        self._stub = stub
        self._user_agent = user_agent
        self._cities = {item["name"].casefold(): item for item in data["cities"]}

    async def assess(self, destination: str, departure_date: date | None = None) -> dict[str, Any]:
        city = self._cities.get(destination.casefold())
        if city is None:
            raise ValueError("Unsupported destination.")
        if self._stub:
            return self._stub_observation(city)
        if not self._user_agent:
            raise ValueError("NWS_USER_AGENT is required for live weather requests.")
        headers = {"User-Agent": self._user_agent, "Accept": "application/geo+json"}
        async with httpx.AsyncClient(
            timeout=8,
            follow_redirects=False,
            headers=headers,
            trust_env=False,
        ) as client:
            point_url = f"{NWS_ROOT}/points/{city['latitude']},{city['longitude']}"
            point = await self._get(client, point_url)
            forecast_url = point.get("properties", {}).get("forecast")
            self._assert_nws_url(forecast_url)
            forecast = await self._get(client, forecast_url)
            alerts = await self._get(client, f"{NWS_ROOT}/alerts/active/area/{city['state']}")
        periods = forecast.get("properties", {}).get("periods", [])
        forecast_period = self._forecast_period(periods, departure_date)
        high_f = forecast_period.get("temperature") if forecast_period else None
        if forecast_period is None or high_f is None:
            return {
                "status": WeatherStatus.UNAVAILABLE.value,
                "high_celsius": None,
                "summary": "NWS returned no forecast for the requested date.",
                "active_alerts": [],
                "source": "National Weather Service",
                "observed_at": datetime.now(UTC).isoformat(),
                "illustrative": False,
            }
        active = [
            feature.get("properties", {}).get("headline", "Active alert")[:160]
            for feature in alerts.get("features", [])[:10]
            if self._alert_applies(feature, departure_date, forecast_period)
        ]
        severe = any(
            token in title.casefold()
            for title in active
            for token in ("tornado", "hurricane", "blizzard", "extreme", "evacuation")
        )
        status = (
            WeatherStatus.NO_GO
            if severe
            else WeatherStatus.CAUTION
            if (high_f is not None and high_f >= 95) or active
            else WeatherStatus.GO
        )
        return {
            "status": status.value,
            "high_celsius": round((high_f - 32) * 5 / 9, 1) if high_f is not None else None,
            "summary": forecast_period.get("shortForecast", "Forecast unavailable")[:300],
            "active_alerts": active,
            "source": "National Weather Service",
            "observed_at": datetime.now(UTC).isoformat(),
            "illustrative": False,
        }

    @staticmethod
    async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        WeatherProvider._assert_nws_url(url)
        try:
            response = await client.get(url)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise RetryableNwsError("NWS request unavailable.") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableNwsError("NWS returned a retryable status.")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid NWS response.")
        return payload

    @staticmethod
    def _assert_nws_url(url: str | None) -> None:
        parsed = urlparse(url or "")
        if parsed.scheme != "https" or parsed.hostname != "api.weather.gov" or parsed.port:
            raise ValueError("NWS returned an unapproved URL.")

    @staticmethod
    def _forecast_period(periods: list, departure_date: date | None) -> dict[str, Any] | None:
        for period in periods:
            if not isinstance(period, dict) or not period.get("isDaytime"):
                continue
            start_time = period.get("startTime")
            if not isinstance(start_time, str):
                continue
            try:
                period_date = datetime.fromisoformat(start_time.replace("Z", "+00:00")).date()
            except ValueError:
                continue
            if departure_date is None or period_date == departure_date:
                return period
        return None

    @staticmethod
    def _alert_applies(
        feature: dict[str, Any], departure_date: date | None, forecast_period: dict[str, Any]
    ) -> bool:
        if departure_date is None:
            return True
        properties = feature.get("properties", {})
        effective = properties.get("effective")
        expires = properties.get("expires")
        if not effective or not expires:
            return True
        period_start = datetime.fromisoformat(forecast_period["startTime"].replace("Z", "+00:00"))
        period_end = datetime.fromisoformat(forecast_period["endTime"].replace("Z", "+00:00"))
        alert_start = datetime.fromisoformat(effective.replace("Z", "+00:00"))
        alert_end = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        return alert_start <= period_end and alert_end >= period_start

    @staticmethod
    def _stub_observation(city: dict[str, Any]) -> dict[str, Any]:
        status = city.get("stub_weather", "GO")
        high_f = city.get("stub_high_f")
        return {
            "status": status,
            "high_celsius": round((high_f - 32) * 5 / 9, 1) if high_f is not None else None,
            "summary": city.get("stub_summary", "Deterministic local weather fixture"),
            "active_alerts": city.get("stub_alerts", []),
            "source": "local deterministic weather fixture",
            "observed_at": datetime.now(UTC).isoformat(),
            "illustrative": True,
        }
