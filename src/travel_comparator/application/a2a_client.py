from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from azure.identity.aio import ManagedIdentityCredential

from travel_comparator.application.ports import AgentPort
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import A2ATaskRequest, A2ATaskResponse, TripRequest


class AgentCallError(RuntimeError):
    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class A2AAgentClient(AgentPort):
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._cards: dict[str, dict[str, Any]] = {}
        self._discovery_locks = {"weather": asyncio.Lock(), "travel": asyncio.Lock()}
        self._managed_identity: ManagedIdentityCredential | None = None

    async def weather(self, destination: str, correlation_id: str, deadline: float) -> dict:
        return await self._call(
            "weather",
            "assess_weather",
            {"destination": destination},
            correlation_id,
            deadline,
            destination,
        )

    async def travel(
        self,
        action: str,
        request: TripRequest,
        correlation_id: str,
        deadline: float,
        constraints: list[dict] | None = None,
    ) -> dict:
        if action not in {"compare_travel", "follow_up"}:
            raise AgentCallError("Unsupported travel action.")
        payload = {"request": request.model_dump(mode="json")}
        if action == "follow_up":
            payload["constraints"] = constraints or []
        return await self._call("travel", action, payload, correlation_id, deadline, action)

    async def ready(self) -> bool:
        try:
            await asyncio.gather(self._discover("weather"), self._discover("travel"))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._managed_identity:
            await self._managed_identity.close()

    async def _call(
        self,
        service: str,
        action: str,
        payload: dict[str, Any],
        correlation_id: str,
        deadline: float,
        label: str,
    ) -> dict[str, Any]:
        await self._discover(service)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Request deadline expired.")
        digest = hashlib.sha256(
            f"{correlation_id}:{service}:{action}:{label}".encode()
        ).hexdigest()[:24]
        task_id = f"{correlation_id[:32]}-{digest}"
        task = A2ATaskRequest(
            task_id=task_id,
            idempotency_key=task_id,
            deadline_seconds=min(30, remaining),
            action=action,  # type: ignore[arg-type]
            payload=payload,
        )
        base_url = self._base_url(service)
        endpoint = base_url.rstrip("/") + "/"
        card = self._cards[service]
        expected = (
            "assess_weather"
            if service == "weather"
            else ("compare_travel" if action == "compare_travel" else "follow_up")
        )
        if not any(skill.get("id") == expected for skill in card.get("skills", [])):
            raise AgentCallError("Configured worker does not advertise the required capability.")
        auth = await self._authorization(service)
        rpc_payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": task_id,
                    "role": "user",
                    "parts": [
                        {"data": task.model_dump(mode="json"), "mediaType": "application/json"}
                    ],
                }
            },
        }
        last_error: Exception | None = None
        for attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Request deadline expired.")
            try:
                async with httpx.AsyncClient(
                    timeout=min(remaining, 10),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        endpoint,
                        json=rpc_payload,
                        headers={
                            "Authorization": f"Bearer {auth}",
                            "X-Correlation-ID": correlation_id,
                            "Idempotency-Key": task.idempotency_key,
                        },
                    )
                if response.status_code in {401, 403, 400, 422}:
                    raise AgentCallError("Worker rejected the task.")
                if response.status_code >= 500 or response.status_code == 429:
                    raise AgentCallError("Worker returned a retryable error.", retryable=True)
                response.raise_for_status()
                envelope = response.json()
                if envelope.get("jsonrpc") != "2.0" or envelope.get("id") != task_id:
                    raise AgentCallError("Worker returned an invalid A2A envelope.")
                data = envelope.get("result", {}).get("artifacts", [])
                task_data = None
                for artifact in data:
                    for part in artifact.get("parts", []):
                        if isinstance(part.get("data"), dict):
                            task_data = part["data"]
                if not task_data:
                    raise AgentCallError("Worker response did not contain a task result.")
                task_response = A2ATaskResponse.model_validate(task_data)
                if task_response.task_id != task_id:
                    raise AgentCallError("Worker task identifier did not match.")
                if task_response.status != "completed":
                    failure = task_response.error.model_dump(mode="json")
                    raise AgentCallError(
                        "Worker task failed.",
                        retryable=bool(failure.get("retryable")),
                    )
                result = task_response.result
                if not isinstance(result, dict):
                    raise AgentCallError("Worker task result is invalid.")
                return result
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
            except AgentCallError as exc:
                last_error = exc
                if not exc.retryable:
                    raise
            if attempt == 0:
                pause = min(0.1, max(0.0, deadline - time.monotonic()))
                if pause:
                    await asyncio.sleep(pause)
        raise AgentCallError(
            f"{service} worker unavailable "
            f"({type(last_error).__name__ if last_error else 'unknown'}).",
            retryable=True,
        )

    async def _discover(self, service: str) -> dict[str, Any]:
        if service in self._cards:
            return self._cards[service]
        async with self._discovery_locks[service]:
            if service in self._cards:
                return self._cards[service]
            token = await self._authorization(service)
            async with httpx.AsyncClient(
                timeout=3,
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    self._base_url(service).rstrip("/") + "/.well-known/agent-card.json",
                    headers={"Authorization": f"Bearer {token}"},
                )
            response.raise_for_status()
            card = response.json()
            if card.get("protocolVersion") != "1.0.0" or not isinstance(card.get("skills"), list):
                raise AgentCallError("Worker Agent Card is incompatible.")
            self._cards[service] = card
            return card

    def _base_url(self, service: str) -> str:
        value = (
            self._settings.weather_agent_url
            if service == "weather"
            else self._settings.travel_agent_url
        )
        parsed = urlparse(value or "")
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.query
            or parsed.fragment
        ):
            raise AgentCallError("Worker endpoint configuration is invalid.")
        if self._settings.app_env != "local" and parsed.scheme != "https":
            raise AgentCallError("Cloud worker endpoints must use HTTPS.")
        return value or ""

    async def _authorization(self, service: str) -> str:
        if self._settings.app_env == "local":
            secret = self._settings.local_coordinator_token
            if secret is None:
                raise AgentCallError("Local coordinator credential is missing.")
            return secret.get_secret_value()
        audience = (
            self._settings.weather_a2a_audience
            if service == "weather"
            else self._settings.travel_a2a_audience
        )
        if not audience:
            raise AgentCallError("Worker audience is not configured.")
        if self._managed_identity is None:
            self._managed_identity = ManagedIdentityCredential(
                client_id=self._settings.managed_identity_client_id
            )
        access_token = await self._managed_identity.get_token(f"{audience.rstrip('/')}/.default")
        return access_token.token
