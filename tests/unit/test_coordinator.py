from __future__ import annotations

import asyncio

import pytest

from tests.conftest import FakeAgents
from travel_comparator.application.coordinator import (
    Coordinator,
    NoUsableComparison,
    RequestRejected,
)
from travel_comparator.contracts.v1 import TripRequest


def comparison_request() -> TripRequest:
    return TripRequest(
        origin="NYC",
        destinations=["Denver", "Austin", "Miami"],
        duration_days=5,
    )


@pytest.mark.asyncio
async def test_parallel_assessment_follow_up_and_deterministic_winner():
    agents = FakeAgents()
    result = await Coordinator(agents).compare(comparison_request(), "corr-1")
    assert agents.max_active >= 2
    assert result.status == "complete"
    assert result.follow_up_performed
    assert result.recommendation.winner == "Denver"
    assert result.comparisons[0].travel.total.amount_minor == 90000
    assert result.comparisons[1].travel.total.amount_minor == 103000
    assert result.comparisons[2].travel.total.amount_minor == 166500
    assert result.comparisons[2].travel.illustrative
    assert "not live or bookable" in result.limitations[0]


@pytest.mark.asyncio
async def test_partial_provider_failure_excludes_city_but_keeps_usable_result():
    result = await Coordinator(FakeAgents(failed_weather={"Miami"})).compare(
        comparison_request(), "corr-2"
    )
    assert result.status == "partial"
    assert result.recommendation.winner == "Denver"
    assert result.comparisons[2].unavailable_sources == ["weather"]


@pytest.mark.asyncio
async def test_all_required_sources_failed_yields_no_usable_comparison():
    with pytest.raises(NoUsableComparison):
        await Coordinator(
            FakeAgents(failed_weather={"Denver", "Austin", "Miami"}, fail_travel=True)
        ).compare(comparison_request())


@pytest.mark.asyncio
async def test_no_go_destinations_have_no_winner():
    agents = FakeAgents()
    original_weather = agents.weather

    async def no_go(city, correlation, deadline):
        result = await original_weather(city, correlation, deadline)
        result["status"] = "NO_GO"
        return result

    agents.weather = no_go
    result = await Coordinator(agents).compare(comparison_request())
    assert result.recommendation.winner is None


@pytest.mark.asyncio
async def test_deadline_is_shared_and_expires_as_timeout():
    agents = FakeAgents()
    original_weather = agents.weather

    async def slow_weather(*args):
        await asyncio.sleep(0.2)
        return await original_weather(*args)

    agents.weather = slow_weather
    with pytest.raises(TimeoutError):
        await Coordinator(agents, request_timeout_seconds=0.03).compare(comparison_request())


def test_payment_data_is_blocked_before_agent_calls():
    agents = FakeAgents()
    request = TripRequest.model_construct(
        origin="4111 1111 1111 1111",
        destinations=["Denver", "Austin"],
        departure_date=None,
        duration_days=5,
        budget=None,
    )
    with pytest.raises(RequestRejected):
        asyncio.run(Coordinator(agents).compare(request))
    assert agents.calls == 0
