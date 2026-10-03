from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from travel_comparator.agents.travel import TravelAdvisor
from travel_comparator.api.main import create_app
from travel_comparator.application.coordinator import Coordinator
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import TripRequest

ROOT = Path(__file__).resolve().parents[1]


class FakeAgents:
    def __init__(self, *, failed_weather: set[str] | None = None, fail_travel: bool = False):
        self.failed_weather = failed_weather or set()
        self.fail_travel = fail_travel
        self.advisor = TravelAdvisor(str(ROOT / "data" / "travel_data.json"))
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._lock = asyncio.Lock()
        self.follow_ups = 0

    async def _enter(self):
        async with self._lock:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.active, self.max_active)

    async def _leave(self):
        async with self._lock:
            self.active -= 1

    async def weather(
        self,
        destination: str,
        correlation_id: str,
        deadline: float,
        departure_date: date | None = None,
    ) -> dict:
        await self._enter()
        try:
            await asyncio.sleep(0.005)
            if destination in self.failed_weather:
                raise ConnectionError("stub unavailable")
            city = next(
                item
                for item in json.loads((ROOT / "data" / "travel_data.json").read_text())["cities"]
                if item["name"] == destination
            )
            from datetime import UTC, datetime

            return {
                "status": city["stub_weather"],
                "high_celsius": 30,
                "summary": "Fixture only",
                "active_alerts": [],
                "source": "test fixture",
                "observed_at": datetime.now(UTC).isoformat(),
                "illustrative": True,
            }
        finally:
            await self._leave()

    async def travel(
        self,
        action: str,
        request: TripRequest,
        correlation_id: str,
        deadline: float,
        constraints: list[dict] | None = None,
    ) -> dict:
        await self._enter()
        try:
            await asyncio.sleep(0.005)
            if self.fail_travel:
                raise ConnectionError("stub unavailable")
            if action == "follow_up":
                self.follow_ups += 1
                return self.advisor.follow_up(request, constraints or [])
            return self.advisor.compare(request)
        finally:
            await self._leave()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="local",
        log_level="INFO",
        api_port=8080,
        weather_agent_url="http://weather-agent:5001",
        travel_agent_url="http://travel-agent:5003",
        request_timeout_seconds=30,
        max_cities=4,
        local_api_token=SecretStr("api-local-token-" + "a" * 32),
        local_coordinator_token=SecretStr("worker-local-token-" + "b" * 32),
        weather_a2a_audience="weather-local",
        travel_a2a_audience="travel-local",
        stub_providers=True,
        travel_data_path=str(ROOT / "data" / "travel_data.json"),
    )


@pytest.fixture
def make_client(settings):
    def factory(agents=None, *, timeout=30):
        agents = agents or FakeAgents()
        coordinator = Coordinator(agents, request_timeout_seconds=timeout)
        app = create_app(settings=settings, coordinator=coordinator)
        client = TestClient(app)
        client.headers.update(
            {"Authorization": f"Bearer {settings.local_api_token.get_secret_value()}"}
        )
        return client, agents

    return factory
