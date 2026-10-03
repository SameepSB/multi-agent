from __future__ import annotations

import pytest
from pydantic import ValidationError

from travel_comparator.contracts.v1 import Money, TravelQuote, TripRequest
from travel_comparator.providers.openai.client import parse_local_query


def test_request_normalizes_places_and_rejects_duplicate_destinations():
    request = TripRequest(
        origin="  New   York ",
        destinations=["Denver", "Austin"],
    )
    assert request.origin == "New York"
    with pytest.raises(ValidationError):
        TripRequest(origin="New York", destinations=["Denver", " denver "])


def test_request_bounds_city_count_and_payment_fields():
    with pytest.raises(ValidationError):
        TripRequest(
            origin="New York",
            destinations=["Denver", "Austin", "Miami", "Seattle", "Phoenix"],
        )
    with pytest.raises(ValidationError):
        TripRequest.model_validate(
            {
                "origin": "New York",
                "destinations": ["Denver", "Austin"],
                "card_number": "4111111111111111",
            }
        )
    with pytest.raises(ValidationError):
        TripRequest(origin="Unknown Origin", destinations=["Denver", "Austin"])
    with pytest.raises(ValidationError):
        TripRequest(origin="New York", destinations=["Denver", "Unsupported City"])


def test_canonical_money_is_minor_units_and_total_is_consistent():
    assert Money(amount_minor=12345).model_dump() == {
        "amount_minor": 12345,
        "currency": "USD",
    }
    with pytest.raises(ValidationError):
        TravelQuote(
            destination="Denver",
            flight=Money(amount_minor=25000),
            hotel_per_night=Money(amount_minor=13000),
            lodging_nights=5,
            total=Money(amount_minor=90000),
            travel_time_hours=4.5,
            source="fixture",
            observed_at="2026-10-03T12:00:00",
        )


def test_local_query_parser_enforces_configured_city_limit_and_payment_policy():
    destinations = ["Denver", "Austin", "Miami"]
    query = "Compare Denver, Austin, and Miami from New York"
    with pytest.raises(ValueError, match="two to 2"):
        parse_local_query(query, destinations, max_cities=2)
    with pytest.raises(ValueError, match="input safety"):
        parse_local_query(
            "Compare Denver and Austin from New York using 4111 1111 1111 1111",
            destinations,
        )
