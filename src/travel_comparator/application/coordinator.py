from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable

from pydantic import ValidationError

from travel_comparator.application.ports import AgentPort
from travel_comparator.contracts.v1 import (
    CityComparison,
    ComparisonResult,
    FollowUpFinding,
    Recommendation,
    ResultStatus,
    TravelQuote,
    TripRequest,
    WeatherObservation,
    WeatherStatus,
    contains_payment_data,
)

logger = logging.getLogger(__name__)
LIMITATIONS = ["Fare and lodging amounts are illustrative estimates, not live or bookable quotes."]


class RequestRejected(ValueError):
    """Raised before fan-out when a request crosses a safety boundary."""


class NoUsableComparison(RuntimeError):
    """Raised when no city has usable travel and weather evidence."""


class Coordinator:
    def __init__(
        self,
        agents: AgentPort,
        request_timeout_seconds: int = 30,
        clock: Callable[[], float] = time.monotonic,
        narrative_provider: Callable[[dict], object] | None = None,
    ) -> None:
        self._agents = agents
        self._timeout = request_timeout_seconds
        self._clock = clock
        self._narrative_provider = narrative_provider

    async def compare(
        self, request: TripRequest, correlation_id: str | None = None
    ) -> ComparisonResult:
        correlation_id = correlation_id or str(uuid.uuid4())
        try:
            async with asyncio.timeout(self._timeout):
                return await self._compare(request, correlation_id)
        except TimeoutError:
            raise

    async def _compare(self, request: TripRequest, correlation_id: str) -> ComparisonResult:
        self._reject_payment(request)
        deadline = self._clock() + self._timeout
        weather_jobs = [
            self._capture(self._agents.weather(city, correlation_id, deadline), "weather")
            for city in request.destinations
        ]
        travel_job = self._capture(
            self._agents.travel("compare_travel", request, correlation_id, deadline),
            "travel",
        )
        weather_results, travel_result = await asyncio.gather(
            asyncio.gather(*weather_jobs), travel_job
        )
        travel_payload = travel_result[0]
        raw_quotes = travel_payload.get("quotes") if isinstance(travel_payload, dict) else None
        quotes = raw_quotes if isinstance(raw_quotes, dict) else {}

        cities: list[CityComparison] = []
        for city, weather_result in zip(request.destinations, weather_results, strict=True):
            raw_weather, weather_error = weather_result
            weather = self._parse_weather(raw_weather)
            if weather and weather.status == WeatherStatus.UNAVAILABLE:
                weather = None
            quote = self._parse_quote(quotes.get(city), city)
            unavailable = []
            if weather is None:
                unavailable.append("weather")
            if quote is None:
                unavailable.append("travel")
            cities.append(
                CityComparison(
                    destination=city,
                    weather=weather,
                    travel=quote,
                    unavailable_sources=unavailable,
                )
            )
            if weather_error:
                logger.info("agent call unavailable service=weather category=%s", weather_error)

        follow_up = self._needs_follow_up(cities)
        follow_up_findings: list[FollowUpFinding] = []
        follow_up_failed = False
        if follow_up:
            constraints = [
                {
                    "destination": city.destination,
                    "weather_status": city.weather.status.value if city.weather else "UNAVAILABLE",
                    "event_severity": city.travel.event_severity if city.travel else "unknown",
                }
                for city in cities
                if city.weather is None
                or city.weather.status != WeatherStatus.GO
                or (city.travel and city.travel.event_severity == "severe")
            ]
            if not constraints:
                constraints = [
                    {
                        "destination": city.destination,
                        "weather_status": city.weather.status.value,
                        "event_severity": city.travel.event_severity,
                    }
                    for city in cities
                    if city.weather and city.travel
                ]
            try:
                async with asyncio.timeout(max(0.001, deadline - self._clock())):
                    follow_up_result = await self._agents.travel(
                        "follow_up", request, correlation_id, deadline, constraints
                    )
                raw_findings = follow_up_result.get("follow_up")
                if not isinstance(raw_findings, list) or len(raw_findings) > len(cities):
                    raise ValueError("Invalid follow-up result.")
                follow_up_findings = [
                    FollowUpFinding.model_validate(finding) for finding in raw_findings
                ]
                expected_destinations = {item["destination"] for item in constraints}
                found_destinations = {finding.destination for finding in follow_up_findings}
                if (
                    len(found_destinations) != len(follow_up_findings)
                    or found_destinations != expected_destinations
                ):
                    raise ValueError("Follow-up result contained an unrequested destination.")
            except Exception as exc:
                if self._clock() >= deadline:
                    raise TimeoutError("Request deadline expired.") from exc
                follow_up_failed = True
                logger.info("follow-up unavailable category=%s", type(exc).__name__)
            if follow_up_failed:
                for city in cities:
                    if city.destination in {item["destination"] for item in constraints}:
                        city.unavailable_sources.append("travel_follow_up")

        complete_candidates = [
            city for city in cities if not city.unavailable_sources and city.weather and city.travel
        ]
        if not complete_candidates:
            raise NoUsableComparison("No destination has complete required-source results.")

        status = (
            ResultStatus.PARTIAL
            if len(complete_candidates) != len(cities)
            else ResultStatus.COMPLETE
        )
        recommendation = self._recommend(complete_candidates)
        narrative = None
        if self._narrative_provider and deadline > self._clock():
            try:
                result_data = {
                    "status": status.value,
                    "comparisons": [city.model_dump(mode="json") for city in cities],
                    "recommendation": recommendation.model_dump(mode="json"),
                }
                async with asyncio.timeout(max(0.001, deadline - self._clock())):
                    narrative = await self._narrative_provider(result_data)  # type: ignore[misc]
                if not isinstance(narrative, str):
                    narrative = None
                if narrative:
                    narrative = " ".join(narrative.split())[:800]
            except Exception as exc:
                if self._clock() >= deadline:
                    raise TimeoutError("Request deadline expired.") from exc
                logger.info("narrative unavailable category=%s", type(exc).__name__)
        return ComparisonResult(
            status=status,
            correlation_id=correlation_id,
            origin=request.origin,
            departure_date=request.departure_date,
            duration_days=request.duration_days,
            comparisons=cities,
            follow_up_performed=follow_up,
            follow_up_findings=follow_up_findings,
            recommendation=recommendation,
            narrative=narrative,
            limitations=LIMITATIONS.copy(),
        )

    @staticmethod
    async def _capture(awaitable: object, source: str) -> tuple[dict | None, str | None]:
        try:
            result = await awaitable  # type: ignore[misc]
            if not isinstance(result, dict):
                return None, f"{source}_invalid"
            return result, None
        except Exception as exc:
            return None, type(exc).__name__

    @staticmethod
    def _parse_weather(payload: object) -> WeatherObservation | None:
        if not isinstance(payload, dict):
            return None
        try:
            return WeatherObservation.model_validate(payload)
        except ValidationError:
            return None

    @staticmethod
    def _parse_quote(payload: object, destination: str) -> TravelQuote | None:
        if not isinstance(payload, dict):
            return None
        try:
            quote = TravelQuote.model_validate(payload)
            return quote if quote.destination.casefold() == destination.casefold() else None
        except ValidationError:
            return None

    @staticmethod
    def _needs_follow_up(cities: list[CityComparison]) -> bool:
        if any(not city.weather or city.weather.status != WeatherStatus.GO for city in cities):
            return True
        if any(city.travel and city.travel.event_severity == "severe" for city in cities):
            return True
        quoted = [city for city in cities if city.travel]
        weather_preferred = next(
            (city for city in quoted if city.weather and city.weather.status == WeatherStatus.GO),
            None,
        )
        cheapest = min(quoted, key=lambda city: city.travel.total.amount_minor, default=None)
        return bool(weather_preferred and cheapest and weather_preferred != cheapest)

    @staticmethod
    def _recommend(cities: list[CityComparison]) -> Recommendation:
        go = [city for city in cities if city.weather.status == WeatherStatus.GO]
        caution = [city for city in cities if city.weather.status == WeatherStatus.CAUTION]
        candidates = go or caution
        if not candidates:
            return Recommendation(
                winner=None,
                reason="All destinations are rated NO_GO; no winner is recommended.",
                warning="Review official weather alerts before booking.",
            )
        winner = min(candidates, key=lambda city: city.travel.total.amount_minor)
        warning = None
        if not go:
            warning = (
                "No destination has GO weather; this lowest-cost CAUTION option carries "
                "weather risk."
            )
        else:
            warning = (
                f"{winner.destination} weather status is CAUTION."
                if winner.weather.status == WeatherStatus.CAUTION
                else None
            )
        return Recommendation(
            winner=winner.destination,
            reason=(
                f"{winner.destination} is the lowest-cost destination with complete price "
                f"and weather evidence among the eligible weather ratings."
            ),
            warning=warning,
        )

    @staticmethod
    def _reject_payment(request: TripRequest) -> None:
        candidates = [request.origin, *request.destinations]
        if any(contains_payment_data(value) for value in candidates):
            raise RequestRejected("Request rejected by input safety policy.")
