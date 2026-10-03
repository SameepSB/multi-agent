from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from travel_comparator.agents.travel import TravelAdvisor
from travel_comparator.contracts.v1 import TripRequest

ROOT = Path(__file__).resolve().parents[2]


def test_reference_data_preserves_documented_nyc_estimates():
    data = json.loads((ROOT / "data" / "travel_data.json").read_text(encoding="utf-8"))
    advisor = TravelAdvisor(str(ROOT / "data" / "travel_data.json"))
    quotes = advisor.compare(
        TripRequest(
            origin="NYC",
            destinations=["Denver", "Austin", "Miami"],
            duration_days=5,
        )
    )["quotes"]
    for city, expected in data["nyc_demo_examples"].items():
        assert quotes[city]["flight"]["amount_minor"] == expected["flight_usd"] * 100
        assert (
            quotes[city]["hotel_per_night"]["amount_minor"] == expected["hotel_usd_per_night"] * 100
        )
        assert quotes[city]["total"]["amount_minor"] == expected["five_day_total_usd"] * 100
        assert quotes[city]["illustrative"] is True
    assert "not provider quotes" in data["provenance"]


def test_event_follow_up_is_date_specific_and_severe_event_is_explicit():
    advisor = TravelAdvisor(str(ROOT / "data" / "travel_data.json"))
    request = TripRequest(
        origin="New York",
        destinations=["Austin", "Miami"],
        departure_date=date(2027, 3, 20),
        duration_days=5,
    )
    quotes = advisor.compare(request)["quotes"]
    assert quotes["Miami"]["event"] == "Miami Music Week / Ultra"
    assert quotes["Miami"]["event_severity"] == "severe"
    assert quotes["Austin"]["event"] is None


def test_event_is_applied_when_trip_overlaps_it_after_departure():
    advisor = TravelAdvisor(str(ROOT / "data" / "travel_data.json"))
    quote = advisor.compare(
        TripRequest(
            origin="New York",
            destinations=["Austin", "Miami"],
            departure_date=date(2027, 3, 5),
            duration_days=5,
        )
    )["quotes"]["Austin"]
    assert quote["event"] == "SXSW"
    assert quote["event_severity"] == "severe"
    assert quote["source"] == "Travel Advisor synthetic reference data v1.0.0"
