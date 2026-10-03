from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from travel_comparator.agents.common import A2AService
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import A2ATaskRequest, Money, TripRequest


class TravelAdvisor:
    def __init__(self, data_path: str) -> None:
        data = json.loads(Path(data_path).read_text(encoding="utf-8"))
        self._cities = {item["name"].casefold(): item for item in data["cities"]}
        self._origins = {origin.casefold(): origin for origin in data["origins"]}
        self._origins.update({"nyc": "New York", "la": "Los Angeles"})

    def compare(self, request: TripRequest) -> dict[str, Any]:
        origin = self._origins.get(request.origin.casefold())
        if origin is None:
            raise ValueError("Origin is not in the supported illustrative estimate data.")
        quotes = {}
        for destination in request.destinations:
            city = self._cities.get(destination.casefold())
            if city is None:
                raise ValueError("Destination is not supported by travel reference data.")
            flight = city["flight_usd"].get(origin)
            if flight is None:
                raise ValueError("No illustrative estimate is available for this route.")
            event = self._event_for(city, request.departure_date)
            hotel_multiplier = 1.0
            if request.departure_date and request.departure_date.month == 3:
                if destination == "Miami":
                    hotel_multiplier *= 1.35
                if destination == "Phoenix":
                    hotel_multiplier *= 1.20
            if event:
                hotel_multiplier *= event["hotel_multiplier"]
            hotel = round(city["hotel_per_night_usd"] * hotel_multiplier)
            nights = request.duration_days
            flight_minor = int(flight * 100)
            hotel_minor = int(hotel * 100)
            quotes[destination] = {
                "destination": destination,
                "flight": Money(amount_minor=flight_minor).model_dump(mode="json"),
                "hotel_per_night": Money(amount_minor=hotel_minor).model_dump(mode="json"),
                "lodging_nights": nights,
                "total": Money(amount_minor=flight_minor + hotel_minor * nights).model_dump(
                    mode="json"
                ),
                "travel_time_hours": city["travel_time_hours"].get(origin, 0),
                "event": event["name"] if event else None,
                "event_severity": event["severity"] if event else "none",
                "source": "versioned synthetic travel reference data",
                "observed_at": datetime.now(UTC).isoformat(),
                "illustrative": True,
            }
        return {"quotes": quotes}

    def follow_up(self, request: TripRequest, constraints: list[dict[str, Any]]) -> dict[str, Any]:
        details = []
        for constraint in constraints:
            name = constraint.get("destination")
            city = self._cities.get(str(name).casefold())
            event = self._event_for(city, request.departure_date) if city else None
            details.append(
                {
                    "destination": name,
                    "weather_status": constraint.get("weather_status"),
                    "event": event["name"] if event else None,
                    "event_severity": event["severity"] if event else "none",
                    "source": "versioned synthetic travel reference data",
                }
            )
        return {"follow_up": details}

    @staticmethod
    def _event_for(city: dict[str, Any], departure: date | None) -> dict[str, Any] | None:
        if departure is None:
            return None
        matches = [
            event
            for event in city["events"]
            if departure.month in event["months"]
            and event["start_day"] <= departure.day <= event["end_day"]
        ]
        return max(
            matches,
            key=lambda event: (
                {"none": 0, "low": 1, "moderate": 2, "severe": 3}[event["severity"]],
                event["hotel_multiplier"],
            ),
            default=None,
        )


def create_service(settings: Settings) -> A2AService:
    advisor = TravelAdvisor(settings.travel_data_path)

    async def handle(task: A2ATaskRequest) -> dict[str, Any]:
        if task.action == "follow_up":
            constraints = task.payload.get("constraints")
            if not isinstance(constraints, list) or len(constraints) > 4:
                raise ValueError("Invalid follow-up constraints.")
            request = TripRequest.model_validate(task.payload.get("request", {}))
            return advisor.follow_up(request, constraints)
        request = TripRequest.model_validate(task.payload.get("request", {}))
        return advisor.compare(request)

    return A2AService(
        name="Travel Comparator Travel Advisor",
        description=(
            "Compares illustrative route, lodging, and event estimates from versioned data."
        ),
        skills=[
            {
                "id": "compare_travel",
                "name": "Travel Cost Comparison",
                "description": "Compare explicitly illustrative route and hotel estimates.",
            },
            {
                "id": "follow_up",
                "name": "Event Impact Check",
                "description": "Recheck requested event impacts under coordinator constraints.",
            },
        ],
        expected_action="compare_travel",
        handler=handle,
    )
