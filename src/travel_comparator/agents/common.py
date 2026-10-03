from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from travel_comparator.contracts.v1 import A2ATaskRequest, A2ATaskResponse, ErrorEnvelope


class TaskCache:
    def __init__(self, max_entries: int = 2048) -> None:
        self._values: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._max_entries = max_entries

    def _get_lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock:
            self._locks.move_to_end(key)
            return lock
        while len(self._locks) >= self._max_entries:
            removable = next(
                (
                    candidate
                    for candidate, candidate_lock in self._locks.items()
                    if not candidate_lock.locked()
                ),
                None,
            )
            if removable is None:
                break
            self._locks.pop(removable)
        lock = asyncio.Lock()
        self._locks[key] = lock
        return lock

    async def run(
        self,
        key: str,
        payload: dict[str, Any],
        action: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        lock = self._get_lock(key)
        async with lock:
            cached = self._values.get(key)
            if cached:
                if cached[0] != digest:
                    raise ValueError("Idempotency key was reused with different input.")
                self._values.move_to_end(key)
                return cached[1]
            result = await action()
            self._values[key] = (digest, result)
            while len(self._values) > self._max_entries:
                evicted, _ = self._values.popitem(last=False)
                old_lock = self._locks.get(evicted)
                if old_lock and not old_lock.locked():
                    self._locks.pop(evicted, None)
            return result


class A2AService:
    def __init__(
        self,
        name: str,
        description: str,
        skills: list[dict[str, str]],
        expected_action: str,
        handler: Callable[[A2ATaskRequest], Awaitable[dict[str, Any]]],
    ) -> None:
        self.name = name
        self.description = description
        self.skills = skills
        self.expected_action = expected_action
        self._handler = handler
        self._cache = TaskCache()
        self._semaphore = asyncio.Semaphore(32)

    def agent_card(self, base_url: str) -> dict[str, Any]:
        return {
            "protocolVersion": "1.0.0",
            "name": self.name,
            "description": self.description,
            "url": base_url,
            "version": "1.0.0",
            "capabilities": {"streaming": False, "pushNotifications": False},
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
            "skills": self.skills,
        }

    async def send(self, data: dict[str, Any]) -> dict[str, Any]:
        task_request = A2ATaskRequest.model_validate(data)
        if task_request.action != self.expected_action and not (
            self.expected_action == "compare_travel" and task_request.action == "follow_up"
        ):
            raise ValueError("Unsupported task action.")

        async def execute() -> dict[str, Any]:
            return await asyncio.wait_for(
                self._handler(task_request), timeout=task_request.deadline_seconds
            )

        task_key = task_request.idempotency_key
        try:
            async with self._semaphore:
                result = await self._cache.run(task_key, data, execute)
            response = A2ATaskResponse(
                task_id=task_request.task_id, status="completed", result=result
            )
        except TimeoutError:
            response = A2ATaskResponse(
                task_id=task_request.task_id,
                status="failed",
                error=ErrorEnvelope(
                    code="AGENT_TIMEOUT",
                    source=self.name,
                    retryable=True,
                    correlation_id=task_request.task_id,
                ),
            )
        except Exception as exc:
            response = A2ATaskResponse(
                task_id=task_request.task_id,
                status="failed",
                error=ErrorEnvelope(
                    code="AGENT_TASK_FAILED",
                    source=self.name,
                    retryable=bool(getattr(exc, "retryable", False)),
                    correlation_id=task_request.task_id,
                ),
            )
        return response.model_dump(mode="json")


def constant_time_secret_match(candidate: str, secret: str) -> bool:
    return secrets.compare_digest(candidate.encode(), secret.encode())


def now_monotonic() -> float:
    return time.monotonic()
