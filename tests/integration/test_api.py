from __future__ import annotations

import json

from tests.conftest import FakeAgents
from travel_comparator.api.main import RequestLimit

VALID_REQUEST = {
    "origin": "New York",
    "destinations": ["Denver", "Austin", "Miami"],
    "duration_days": 5,
}


def test_api_complete_comparison_and_server_correlation(make_client):
    client, agents = make_client()
    response = client.post("/api/v1/comparisons", json=VALID_REQUEST)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "complete"
    assert payload["schema_version"] == "1.0.0"
    assert payload["recommendation"]["winner"] == "Denver"
    assert payload["follow_up_performed"] is True
    assert payload["follow_up_findings"][0]["destination"] == "Austin"
    assert response.headers["X-Correlation-ID"] == payload["correlation_id"]
    assert agents.follow_ups == 1


def test_api_partial_and_failed_source_outcomes(make_client):
    client, _ = make_client(FakeAgents(failed_weather={"Miami"}))
    partial = client.post("/api/v1/comparisons", json=VALID_REQUEST)
    assert partial.status_code == 200
    assert partial.json()["status"] == "partial"
    assert partial.json()["comparisons"][2]["unavailable_sources"] == ["weather"]

    failed_client, _ = make_client(
        FakeAgents(failed_weather={"Denver", "Austin", "Miami"}, fail_travel=True)
    )
    failed = failed_client.post("/api/v1/comparisons", json=VALID_REQUEST)
    assert failed.status_code == 502
    assert failed.json()["code"] == "NO_USABLE_COMPARISON"


def test_api_denies_anonymous_user_without_fan_out(make_client):
    client, agents = make_client()
    client.headers.pop("Authorization")
    response = client.post("/api/v1/comparisons", json=VALID_REQUEST)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert agents.calls == 0


def test_api_rejects_invalid_payment_and_oversized_requests_before_fan_out(make_client):
    client, agents = make_client()
    invalid = client.post(
        "/api/v1/comparisons",
        json={"origin": "New York", "destinations": ["Denver", "Denver"]},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "INPUT_INVALID"
    assert agents.calls == 0

    payment = client.post(
        "/api/v1/comparisons",
        content=json.dumps(
            {"origin": "New York", "destinations": ["Denver", "Austin"], "cvv": "123"}
        ),
        headers={"Content-Type": "application/json"},
    )
    assert payment.status_code == 422
    assert agents.calls == 0

    unsupported = client.post(
        "/api/v1/comparisons",
        json={
            "origin": "New York",
            "destinations": ["Denver", "Somewhere Else"],
        },
    )
    assert unsupported.status_code == 422
    assert agents.calls == 0

    oversized = client.post("/api/v1/comparisons", content=b"x" * 40_000)
    assert oversized.status_code == 413
    assert agents.calls == 0


def test_api_timeout_returns_504(make_client):
    client, agents = make_client(timeout=0.03)
    original_weather = agents.weather

    async def slow_weather(*args):
        import asyncio

        await asyncio.sleep(0.2)
        return await original_weather(*args)

    agents.weather = slow_weather
    response = client.post("/api/v1/comparisons", json=VALID_REQUEST)
    assert response.status_code == 504
    assert response.json()["code"] == "DEADLINE_EXCEEDED"


def test_api_idempotency_key_replays_correlation_and_rejects_changed_body(make_client):
    client, agents = make_client()
    first = client.post(
        "/api/v1/comparisons",
        json=VALID_REQUEST,
        headers={"Idempotency-Key": "same-comparison-key"},
    )
    calls_after_first = agents.calls
    replay = client.post(
        "/api/v1/comparisons",
        json=VALID_REQUEST,
        headers={"Idempotency-Key": "same-comparison-key"},
    )
    conflict = client.post(
        "/api/v1/comparisons",
        json={**VALID_REQUEST, "duration_days": 6},
        headers={"Idempotency-Key": "same-comparison-key"},
    )
    assert replay.json()["correlation_id"] == first.json()["correlation_id"]
    assert replay.json() == first.json()
    assert agents.calls == calls_after_first
    assert conflict.status_code == 409


def test_rate_limit_bounds_distinct_principal_state(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("travel_comparator.api.main.time.monotonic", lambda: now[0])
    limiter = RequestLimit(maximum=2, window_seconds=60, max_principals=2)

    assert limiter.allowed("user-1")
    assert limiter.allowed("user-2")
    assert not limiter.allowed("user-3")
    assert len(limiter._requests) == 2

    now[0] = 61.0
    assert limiter.allowed("user-3")
    assert len(limiter._requests) == 1
