from __future__ import annotations

import asyncio
import json
import time
from datetime import date

import httpx
import pytest

from travel_comparator.agents.common import A2AService, TaskCache
from travel_comparator.application.a2a_client import A2AAgentClient
from travel_comparator.contracts.v1 import A2ATaskRequest


@pytest.mark.asyncio
async def test_task_cache_reuses_completed_idempotent_work():
    cache = TaskCache()
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return {"value": "done"}

    first = await cache.run("key-1", {"action": "test"}, operation)
    second = await cache.run("key-1", {"action": "test"}, operation)
    assert first == second
    assert calls == 1


@pytest.mark.asyncio
async def test_task_cache_rejects_key_reuse_for_different_input():
    cache = TaskCache()

    async def operation():
        return {"value": True}

    await cache.run("key-1", {"action": "one"}, operation)
    with pytest.raises(ValueError):
        await cache.run("key-1", {"action": "two"}, operation)


@pytest.mark.asyncio
async def test_a2a_task_response_uses_common_correlation_error_envelope():
    async def fail(_):
        raise ValueError("private error details must not escape")

    service = A2AService("example", "test", [], "assess_weather", fail)
    task = A2ATaskRequest(
        task_id="task-1",
        idempotency_key="task-1",
        deadline_seconds=3,
        action="assess_weather",
        payload={"destination": "Denver"},
    )
    response = await service.send(task.model_dump(mode="json"))
    assert response["status"] == "failed"
    assert response["error"] == {
        "code": "AGENT_TASK_FAILED",
        "source": "example",
        "retryable": False,
        "correlation_id": "task-1",
    }


@pytest.mark.asyncio
async def test_agent_retries_one_retryable_call_with_same_idempotency_key(settings):
    class RetryOnceTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.calls = 0
            self.keys: list[str | None] = []
            self.rpc_payloads: list[dict] = []

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            self.keys.append(request.headers.get("Idempotency-Key"))
            self.rpc_payloads.append(json.loads(request.content))
            if self.calls == 1:
                return httpx.Response(503, request=request)
            rpc_id = json.loads(request.content)["id"]
            task_result = {
                "schema_version": "1.0.0",
                "task_id": rpc_id,
                "status": "completed",
                "result": {"status": "GO"},
                "error": None,
            }
            body = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "artifacts": [
                        {"parts": [{"data": task_result, "mediaType": "application/json"}]}
                    ]
                },
            }
            return httpx.Response(200, json=body, request=request)

        async def aclose(self) -> None:
            return None

    transport = RetryOnceTransport()
    client = A2AAgentClient(settings, transport=transport)
    client._cards["weather"] = {
        "protocolVersion": "1.0.0",
        "skills": [{"id": "assess_weather"}],
    }
    result = await client.weather(
        "Denver",
        "correlation-1",
        time.monotonic() + 2,
        departure_date=date(2027, 3, 5),
    )
    assert result == {"status": "GO"}
    assert transport.calls == 2
    assert transport.keys[0] == transport.keys[1]
    data_part = transport.rpc_payloads[0]["params"]["message"]["parts"][0]["data"]
    assert data_part["payload"]["departure_date"] == "2027-03-05"
