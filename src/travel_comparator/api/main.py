from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from travel_comparator.api.auth import api_auth_dependency
from travel_comparator.application.a2a_client import A2AAgentClient
from travel_comparator.application.coordinator import (
    Coordinator,
    NoUsableComparison,
    RequestRejected,
)
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import (
    ComparisonResult,
    ErrorEnvelope,
    TripRequest,
    contains_payment_data,
)
from travel_comparator.providers.openai.client import OpenAIAdapter

logger = logging.getLogger("travel_comparator.api")


class RequestLimit:
    def __init__(self, maximum: int = 60, window_seconds: int = 60) -> None:
        self.maximum = maximum
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        values = self._requests.setdefault(key, deque())
        while values and values[0] <= now - self.window_seconds:
            values.popleft()
        if len(values) >= self.maximum:
            return False
        values.append(now)
        if len(self._requests) > 10_000:
            for client, requests in list(self._requests.items()):
                if not requests or requests[-1] <= now - self.window_seconds:
                    self._requests.pop(client, None)
        return True


class IdempotencyRegistry:
    def __init__(self, max_entries: int = 4096) -> None:
        self._items: OrderedDict[str, tuple[str, str, ComparisonResult | None]] = OrderedDict()
        self._locks: OrderedDict[str, asyncio.Lock] = OrderedDict()
        self._max_entries = max_entries

    def _lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is not None:
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

    async def execute(
        self,
        key: str,
        body: bytes,
        operation: Callable[[str], Awaitable[ComparisonResult]],
    ) -> tuple[str, ComparisonResult]:
        digest = hashlib.sha256(body).hexdigest()
        async with self._lock_for(key):
            current = self._items.get(key)
            if current:
                if current[0] != digest:
                    raise RequestRejected("Idempotency key was reused with different input.")
                self._items.move_to_end(key)
                if current[2] is not None:
                    return current[1], current[2]
            correlation_id = str(uuid.uuid4())
            try:
                result = await operation(correlation_id)
            except Exception:
                if current is None:
                    self._items.pop(key, None)
                raise
            self._items[key] = (digest, correlation_id, result)
            self._items.move_to_end(key)
            while len(self._items) > self._max_entries:
                self._items.popitem(last=False)
            return correlation_id, result


def create_app(
    settings: Settings | None = None,
    coordinator: Coordinator | None = None,
    agent_client: A2AAgentClient | None = None,
) -> FastAPI:
    settings = settings or Settings()
    settings.validate_for("api")
    openai = None
    if coordinator is None:
        settings.validate_for("coordinator")
        agent_client = agent_client or A2AAgentClient(settings)
        openai = (
            None
            if settings.stub_providers
            else OpenAIAdapter(settings.openai_api_key.get_secret_value(), settings.openai_model)
        )
        coordinator = Coordinator(
            agent_client,
            request_timeout_seconds=settings.request_timeout_seconds,
            narrative_provider=openai.explain if openai else None,
        )
    auth = api_auth_dependency(settings)
    request_limit = RequestLimit()
    idempotency = IdempotencyRegistry()

    async def authenticated_user(request: Request) -> dict[str, Any]:
        claims = await auth(request)
        principal = claims.get("oid") or claims.get("sub")
        if not isinstance(principal, str) or not 1 <= len(principal) <= 200:
            raise HTTPException(
                status_code=401,
                detail=ErrorEnvelope(
                    code="UNAUTHORIZED",
                    source="api_auth",
                    retryable=False,
                    correlation_id=request.state.correlation_id,
                ).model_dump(mode="json"),
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.authenticated_user = claims
        if not request_limit.allowed(principal):
            raise HTTPException(
                status_code=429,
                detail=ErrorEnvelope(
                    code="RATE_LIMITED",
                    source="api",
                    retryable=False,
                    correlation_id=request.state.correlation_id,
                ).model_dump(mode="json"),
                headers={"Retry-After": "60"},
            )
        return claims

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if agent_client:
            await agent_client.close()
        if openai:
            await openai.close()

    app = FastAPI(
        title="Travel Comparator API",
        version="1.0.0",
        docs_url=None if settings.app_env == "production" else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.agent_client = agent_client
    app.state.settings = settings
    app.state.openai_adapter = openai

    @app.middleware("http")
    async def request_boundary(request: Request, call_next):
        request.state.correlation_id = str(uuid.uuid4())
        if request.url.path in {"/health/live", "/health/ready"}:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = request.state.correlation_id
            return response
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.max_request_bytes:
                    return _error_response(
                        413,
                        "REQUEST_TOO_LARGE",
                        "api",
                        False,
                        request.state.correlation_id,
                        "Request exceeds the allowed size.",
                    )
            except ValueError:
                return _error_response(
                    400,
                    "INVALID_CONTENT_LENGTH",
                    "api",
                    False,
                    request.state.correlation_id,
                    "Invalid request framing.",
                )
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > settings.max_request_bytes:
                return _error_response(
                    413,
                    "REQUEST_TOO_LARGE",
                    "api",
                    False,
                    request.state.correlation_id,
                    "Request exceeds the allowed size.",
                )
        request._body = bytes(body)

        async def receive():
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        request._receive = receive
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        return response

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/health/ready")
    async def readiness() -> JSONResponse:
        ready = await agent_client.ready() if agent_client else True
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready"},
        )

    @app.post(
        "/api/v1/comparisons",
        response_model=ComparisonResult,
        dependencies=[Depends(authenticated_user)],
    )
    async def compare(trip: TripRequest, request: Request) -> JSONResponse:
        raw_key = request.headers.get("idempotency-key", "")
        if raw_key and (len(raw_key) > 128 or not raw_key.isascii()):
            return _error_response(
                400,
                "INVALID_IDEMPOTENCY_KEY",
                "api",
                False,
                request.state.correlation_id,
            )
        if _contains_payment_field(request._body) or any(
            contains_payment_data(value) for value in [trip.origin, *trip.destinations]
        ):
            return _error_response(
                422,
                "PAYMENT_DATA_REJECTED",
                "input_validation",
                False,
                request.state.correlation_id,
                "Payment data is not accepted.",
            )
        if len(trip.destinations) > settings.max_cities:
            return _error_response(
                422,
                "TOO_MANY_DESTINATIONS",
                "input_validation",
                False,
                request.state.correlation_id,
                "Destination count exceeds configured maximum.",
            )
        try:
            principal = request.state.authenticated_user.get(
                "oid"
            ) or request.state.authenticated_user.get("sub")
            idempotency_key = f"{principal}:{raw_key or request.state.correlation_id}"

            async def compare_once(correlation_id: str) -> ComparisonResult:
                request.state.correlation_id = correlation_id
                return await coordinator.compare(trip, correlation_id)

            correlation_id, result = await idempotency.execute(
                idempotency_key,
                request._body,
                compare_once,
            )
            request.state.correlation_id = correlation_id
        except RequestRejected:
            return _error_response(
                409,
                "IDEMPOTENCY_CONFLICT",
                "api",
                False,
                request.state.correlation_id,
            )
        return JSONResponse(
            status_code=200,
            content=result.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        return _error_response(
            422,
            "INPUT_INVALID",
            "input_validation",
            False,
            getattr(request.state, "correlation_id", str(uuid.uuid4())),
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and {
            "code",
            "source",
            "retryable",
            "correlation_id",
        }.issubset(detail):
            return JSONResponse(
                status_code=exc.status_code,
                content=detail,
                headers=exc.headers,
            )
        return _error_response(
            exc.status_code,
            "HTTP_ERROR",
            "api",
            False,
            getattr(request.state, "correlation_id", str(uuid.uuid4())),
        )

    @app.exception_handler(RequestRejected)
    async def rejected(request: Request, _: RequestRejected) -> JSONResponse:
        return _error_response(
            422,
            "INPUT_REJECTED",
            "input_validation",
            False,
            getattr(request.state, "correlation_id", str(uuid.uuid4())),
        )

    @app.exception_handler(NoUsableComparison)
    async def no_result(request: Request, _: NoUsableComparison) -> JSONResponse:
        return _error_response(
            502,
            "NO_USABLE_COMPARISON",
            "coordinator",
            False,
            getattr(request.state, "correlation_id", str(uuid.uuid4())),
        )

    @app.exception_handler(TimeoutError)
    async def timeout(request: Request, _: TimeoutError) -> JSONResponse:
        return _error_response(
            504,
            "DEADLINE_EXCEEDED",
            "coordinator",
            True,
            getattr(request.state, "correlation_id", str(uuid.uuid4())),
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "request failed service=api category=%s",
            type(exc).__name__,
        )
        return _error_response(
            500,
            "INTERNAL_ERROR",
            "api",
            False,
            getattr(request.state, "correlation_id", str(uuid.uuid4())),
        )

    return app


def _contains_payment_field(raw_body: bytes) -> bool:
    from travel_comparator.contracts.v1 import PAYMENT_FIELD_NAMES

    try:
        value = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False

    def inspect(item: Any) -> bool:
        if isinstance(item, dict):
            return any(
                str(key).casefold() in PAYMENT_FIELD_NAMES or inspect(child)
                for key, child in item.items()
            )
        if isinstance(item, list):
            return any(inspect(child) for child in item)
        if isinstance(item, str):
            return contains_payment_data(item)
        return False

    return inspect(value)


def _error_response(
    status_code: int,
    code: str,
    source: str,
    retryable: bool,
    correlation_id: str,
    message: str = "",
) -> JSONResponse:
    envelope = ErrorEnvelope(
        code=code,
        source=source,
        retryable=retryable,
        correlation_id=correlation_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={"X-Correlation-ID": correlation_id},
    )
