from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from travel_comparator.agents.common import A2AService
from travel_comparator.agents.http_app import create_worker_app


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"jsonrpc": "2.0", "method": "message/send", "params": []},
        {"jsonrpc": "2.0", "method": "message/send", "params": {"message": []}},
        {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {"message": {"parts": ["invalid"]}},
        },
    ],
)
def test_worker_returns_bad_request_for_malformed_json_shapes(settings, payload):
    service = A2AService("test", "test", [], "assess_weather", lambda _task: {})
    app = create_worker_app(
        settings,
        settings.weather_a2a_audience,
        service,
        "http://weather-agent:5001",
    )

    with TestClient(app) as client:
        response = client.post(
            "/",
            json=payload,
            headers={
                "Authorization": "Bearer " + settings.local_coordinator_token.get_secret_value()
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["data"]["code"] == "A2A_INVALID_REQUEST"
