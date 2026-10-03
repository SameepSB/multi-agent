"""Canonical v1 request, domain-result, and error contracts."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from travel_comparator.contracts.locations import DESTINATIONS, ORIGINS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResultStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class WeatherStatus(StrEnum):
    GO = "GO"
    CAUTION = "CAUTION"
    NO_GO = "NO_GO"
    UNAVAILABLE = "UNAVAILABLE"


class Money(StrictModel):
    amount_minor: Annotated[int, Field(ge=0, le=100_000_000)]
    currency: Literal["USD"] = "USD"


class TripRequest(StrictModel):
    origin: Annotated[str, Field(min_length=2, max_length=80)]
    destinations: Annotated[list[str], Field(min_length=2, max_length=4)]
    departure_date: date | None = None
    duration_days: Annotated[int, Field(ge=1, le=21)] = 5
    budget: Money | None = None

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        normalized = normalize_place(value)
        canonical = ORIGINS.get(normalized.casefold())
        if canonical is None:
            raise ValueError("origin is not supported")
        return canonical

    @field_validator("destinations")
    @classmethod
    def validate_destinations(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            place = normalize_place(value)
            canonical = DESTINATIONS.get(place.casefold())
            if canonical is None:
                raise ValueError("destination is not supported")
            normalized.append(canonical)
        if len({value.casefold() for value in normalized}) != len(normalized):
            raise ValueError("destinations must be unique")
        return normalized


class WeatherObservation(StrictModel):
    status: WeatherStatus
    high_celsius: float | None = None
    summary: Annotated[str, Field(max_length=300)]
    active_alerts: Annotated[list[Annotated[str, Field(max_length=160)]], Field(max_length=10)] = (
        Field(default_factory=list)
    )
    source: Annotated[str, Field(min_length=1, max_length=80)]
    observed_at: str
    illustrative: bool = False

    @field_validator("observed_at")
    @classmethod
    def offset_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("observed_at must include a UTC offset")
        return value


class TravelQuote(StrictModel):
    destination: str
    flight: Money
    hotel_per_night: Money
    lodging_nights: Annotated[int, Field(ge=1, le=21)]
    total: Money
    travel_time_hours: Annotated[float, Field(ge=0, le=100)]
    event: Annotated[str | None, Field(max_length=160)] = None
    event_severity: Literal["none", "low", "moderate", "severe"] = "none"
    source: Annotated[str, Field(min_length=1, max_length=80)]
    observed_at: str
    illustrative: bool = True

    @field_validator("observed_at")
    @classmethod
    def offset_timestamp(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("observed_at must include a UTC offset")
        return value

    @model_validator(mode="after")
    def total_matches_components(self) -> TravelQuote:
        expected = (
            self.flight.amount_minor + self.hotel_per_night.amount_minor * self.lodging_nights
        )
        if expected != self.total.amount_minor:
            raise ValueError("total must equal flight plus hotel per night times nights")
        return self


class CityComparison(StrictModel):
    destination: str
    weather: WeatherObservation | None = None
    travel: TravelQuote | None = None
    unavailable_sources: Annotated[list[str], Field(max_length=3)] = Field(default_factory=list)


class FollowUpFinding(StrictModel):
    destination: str
    weather_status: WeatherStatus
    event: Annotated[str | None, Field(max_length=160)] = None
    event_severity: Literal["none", "low", "moderate", "severe"]
    source: Annotated[str, Field(min_length=1, max_length=80)]


class Recommendation(StrictModel):
    winner: str | None = None
    reason: Annotated[str, Field(max_length=600)]
    warning: str | None = None


class ComparisonResult(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    status: ResultStatus
    correlation_id: str
    origin: str
    departure_date: date | None = None
    duration_days: int
    comparisons: Annotated[list[CityComparison], Field(min_length=2, max_length=4)]
    follow_up_performed: bool
    follow_up_findings: Annotated[list[FollowUpFinding], Field(max_length=4)] = Field(
        default_factory=list
    )
    recommendation: Recommendation
    narrative: Annotated[str | None, Field(max_length=800)] = None
    limitations: Annotated[list[str], Field(max_length=10)] = Field(default_factory=list)


class ErrorEnvelope(StrictModel):
    code: Annotated[str, Field(min_length=1, max_length=80)]
    source: Annotated[str, Field(min_length=1, max_length=80)]
    retryable: bool
    correlation_id: str


class A2ATaskRequest(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: Annotated[str, Field(min_length=1, max_length=100)]
    idempotency_key: Annotated[str, Field(min_length=1, max_length=128)]
    deadline_seconds: Annotated[float, Field(gt=0, le=30)]
    action: Literal["assess_weather", "compare_travel", "follow_up"]
    payload: dict


class A2ATaskResponse(StrictModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    task_id: str
    status: Literal["completed", "failed"]
    result: dict | None = None
    error: ErrorEnvelope | None = None

    @model_validator(mode="after")
    def validates_outcome(self) -> A2ATaskResponse:
        if self.status == "completed" and (self.result is None or self.error is not None):
            raise ValueError("completed tasks require a result and no error")
        if self.status == "failed" and (self.error is None or self.result is not None):
            raise ValueError("failed tasks require an error and no result")
        return self


PLACE_PATTERN = re.compile(r"^[\w .,'-]{2,80}$", re.UNICODE)
PAN_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PAYMENT_FIELD_NAMES = {
    "pan",
    "card_number",
    "credit_card",
    "cvv",
    "cvc",
    "security_code",
    "payment_token",
    "track_data",
    "pin_block",
}


def normalize_place(value: str) -> str:
    normalized = " ".join(value.split())
    if not PLACE_PATTERN.fullmatch(normalized):
        raise ValueError("place contains unsupported characters")
    return normalized


def contains_payment_data(value: str) -> bool:
    return PAN_PATTERN.search(value) is not None
