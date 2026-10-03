from __future__ import annotations

from travel_comparator.agents.http_app import create_worker_app
from travel_comparator.agents.weather import create_service
from travel_comparator.config import Settings


def create_app():
    settings = Settings()
    settings.validate_for("weather")
    return create_worker_app(
        settings,
        settings.weather_a2a_audience or "",
        create_service(settings),
        "http://weather-agent:5001",
    )
