from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from travel_comparator.agents.http_app import create_worker_app
from travel_comparator.agents.travel import create_service as create_travel_service
from travel_comparator.agents.weather import create_service as create_weather_service
from travel_comparator.api.main import create_app
from travel_comparator.application.a2a_client import A2AAgentClient

ROOT = Path(__file__).resolve().parents[2]
WEATHER_URL = "http://weather.test:5001"
TRAVEL_URL = "http://travel.test:5003"


class WorkerTransport(httpx.AsyncBaseTransport):
    def __init__(self, workers: dict[str, FastAPI]) -> None:
        self._workers = workers

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        app = self._workers[request.url.host]
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        return await transport.handle_async_request(request)

    async def aclose(self) -> None:
        return None


def test_api_to_a2a_workers_to_mcp_stub_end_to_end(settings):
    settings.weather_agent_url = WEATHER_URL
    settings.travel_agent_url = TRAVEL_URL
    settings.travel_data_path = str(ROOT / "data" / "travel_data.json")
    settings.openai_api_key = SecretStr("replace-me")
    weather_service = create_weather_service(settings)
    travel_service = create_travel_service(settings)
    workers = {
        "weather.test": create_worker_app(
            settings,
            settings.weather_a2a_audience,
            weather_service,
            WEATHER_URL,
        ),
        "travel.test": create_worker_app(
            settings,
            settings.travel_a2a_audience,
            travel_service,
            TRAVEL_URL,
        ),
    }
    worker_client = A2AAgentClient(settings, transport=WorkerTransport(workers))
    app = create_app(settings=settings, agent_client=worker_client)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/comparisons",
            json={
                "origin": "New York",
                "destinations": ["Denver", "Austin", "Miami"],
                "duration_days": 5,
            },
            headers={
                "Authorization": (f"Bearer {settings.local_api_token.get_secret_value()}"),
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "complete"
    assert result["recommendation"]["winner"] == "Denver"
    assert [city["travel"]["total"]["amount_minor"] for city in result["comparisons"]] == [
        90_000,
        103_000,
        166_500,
    ]
    assert all(city["travel"]["illustrative"] for city in result["comparisons"])
    assert all(
        city["weather"]["source"] == "local deterministic weather fixture"
        for city in result["comparisons"]
    )
