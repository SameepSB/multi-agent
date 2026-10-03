from __future__ import annotations

import asyncio
from pathlib import Path

from travel_comparator.agents.weather import MCPWeatherClient
from travel_comparator.config import Settings


def test_weather_agent_uses_private_mcp_stdio_fixture_without_live_network():
    data_file = Path(__file__).resolve().parents[2] / "data" / "travel_data.json"
    settings = Settings(
        app_env="local",
        log_level="INFO",
        request_timeout_seconds=30,
        max_cities=4,
        stub_providers=True,
        travel_data_path=str(data_file),
    )
    observation = asyncio.run(MCPWeatherClient(settings).assess("Denver", 5))
    assert observation["source"] == "local deterministic weather fixture"
    assert observation["status"] == "GO"
    assert observation["illustrative"] is True
