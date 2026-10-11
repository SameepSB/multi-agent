from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from travel_comparator.agents.common import A2AService
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import A2ATaskRequest, Money, TripRequest
from travel_comparator.places import (
    ESTIMATE_SOURCE,
    KNOWN_ORIGIN_COORDINATES,
    Geocoder,
    Place,
    UnknownPlaceError,
    distance_km,
    estimate_flight_usd,
    estimate_hotel_usd,
    estimate_travel_hours,
)
from travel_comparator.providers.serpapi import (
    SOURCE as LIVE_SOURCE,
)
from travel_comparator.providers.serpapi import (
    LiveProviderError,
    SerpApiTravelProvider,
)


class TravelAdvisor:
    def __init__(self, data_path: str) -> None:
        data = json.loads(Path(data_path).read_text(encoding="utf-8"))
        self._source = f"{data['data_owner']} synthetic reference data v{data['data_version']}"
        self._cities = {item["name"].casefold(): item for item in data["cities"]}
        self._origins = {origin.casefold(): origin for origin in data["origins"]}
        self._origins.update({"nyc": "New York", "la": "Los Angeles"})

    def missing_places(self, request: TripRequest) -> list[str]:
        """Names that need a geocoding lookup because the curated data cannot price them."""
        needed: list[str] = []
        origin_known = request.origin in self._origins.values()
        if not origin_known:
            needed.append(request.origin)
        for destination in request.destinations:
            city = self._cities.get(destination.casefold())
            if city is None or not origin_known:
                needed.append(destination)
        return needed

    def compare(
        self, request: TripRequest, places: dict[str, Place] | None = None
    ) -> dict[str, Any]:
        places = places or {}
        origin = self._origins.get(request.origin.casefold(), request.origin)
        quotes = {}
        for destination in request.destinations:
            city = self._cities.get(destination.casefold())
            curated_flight = city["flight_usd"].get(origin) if city else None
            if city is not None and curated_flight is not None:
                flight, hours, hotel_base, source = (
                    curated_flight,
                    city["travel_time_hours"].get(origin, 0),
                    city["hotel_per_night_usd"],
                    self._source,
                )
            else:
                estimate = self._estimate(origin, destination, city, places)
                if estimate is None:
                    continue
                flight, hours, hotel_base = estimate
                source = ESTIMATE_SOURCE
            event = (
                self._event_for(city, request.departure_date, request.duration_days)
                if city
                else None
            )
            hotel_multiplier = 1.0
            if request.departure_date and request.departure_date.month == 3:
                if destination == "Miami":
                    hotel_multiplier *= 1.35
                if destination == "Phoenix":
                    hotel_multiplier *= 1.20
            if event:
                hotel_multiplier *= event["hotel_multiplier"]
            hotel = round(hotel_base * hotel_multiplier)
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
                "travel_time_hours": hours,
                "event": event["name"] if event else None,
                "event_severity": event["severity"] if event else "none",
                "source": source,
                "observed_at": datetime.now(UTC).isoformat(),
                "illustrative": True,
            }
        return {"quotes": quotes}

    @staticmethod
    def _estimate(
        origin: str,
        destination: str,
        city: dict[str, Any] | None,
        places: dict[str, Place],
    ) -> tuple[int, float, int] | None:
        """Distance and country-tier estimate; None when a place could not be resolved."""
        if origin in KNOWN_ORIGIN_COORDINATES:
            lat, lon, origin_country = KNOWN_ORIGIN_COORDINATES[origin]
            origin_point: Place | None = Place(origin, lat, lon, origin_country)
        else:
            origin_point = places.get(origin)
        if city is not None:
            destination_point: Place | None = Place(
                destination, city["latitude"], city["longitude"], "US"
            )
            hotel = city["hotel_per_night_usd"]
        else:
            destination_point = places.get(destination)
            hotel = estimate_hotel_usd(destination_point.country_code) if destination_point else 0
        if origin_point is None or destination_point is None:
            return None
        km = distance_km(origin_point, destination_point)
        international = origin_point.country_code != destination_point.country_code
        return estimate_flight_usd(km, international), estimate_travel_hours(km), hotel

    def follow_up(self, request: TripRequest, constraints: list[dict[str, Any]]) -> dict[str, Any]:
        details = []
        for constraint in constraints:
            name = constraint.get("destination")
            city = self._cities.get(str(name).casefold())
            event = (
                self._event_for(city, request.departure_date, request.duration_days)
                if city
                else None
            )
            details.append(
                {
                    "destination": name,
                    "weather_status": constraint.get("weather_status"),
                    "event": event["name"] if event else None,
                    "event_severity": event["severity"] if event else "none",
                    "source": self._source,
                }
            )
        return {"follow_up": details}

    @staticmethod
    def _event_for(
        city: dict[str, Any], departure: date | None, duration_days: int
    ) -> dict[str, Any] | None:
        if departure is None:
            return None
        trip_dates = (departure + timedelta(days=offset) for offset in range(duration_days))
        trip_month_days = {(trip_date.month, trip_date.day) for trip_date in trip_dates}
        matches = [
            event
            for event in city["events"]
            if any(
                month in event["months"] and event["start_day"] <= day <= event["end_day"]
                for month, day in trip_month_days
            )
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
    geocoder = Geocoder()
    live = (
        SerpApiTravelProvider(settings.serpapi_api_key.get_secret_value())
        if settings.serpapi_api_key and not settings.stub_providers
        else None
    )

    async def handle(task: A2ATaskRequest) -> dict[str, Any]:
        if task.action == "follow_up":
            constraints = task.payload.get("constraints")
            if not isinstance(constraints, list) or len(constraints) > 4:
                raise ValueError("Invalid follow-up constraints.")
            request = TripRequest.model_validate(task.payload.get("request", {}))
            return advisor.follow_up(request, constraints)
        request = TripRequest.model_validate(task.payload.get("request", {}))
        places: dict[str, Place] = {}
        for name in advisor.missing_places(request):
            try:
                places[name] = await geocoder.lookup(name)
            except UnknownPlaceError:
                continue
        result = advisor.compare(request, places)
        if live is not None and request.departure_date is not None:
            for destination, quote in result["quotes"].items():
                try:
                    live_quote = await live.quote(
                        request.origin,
                        destination,
                        request.departure_date,
                        request.duration_days,
                    )
                except LiveProviderError:
                    continue
                flight = live_quote.flight_usd_minor
                hotel = live_quote.hotel_per_night_usd_minor
                quote.update(
                    flight=Money(amount_minor=flight).model_dump(mode="json"),
                    hotel_per_night=Money(amount_minor=hotel).model_dump(mode="json"),
                    total=Money(amount_minor=flight + hotel * quote["lodging_nights"]).model_dump(
                        mode="json"
                    ),
                    travel_time_hours=live_quote.travel_time_hours,
                    source=LIVE_SOURCE,
                    observed_at=live_quote.observed_at,
                    illustrative=False,
                )
        return result

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
