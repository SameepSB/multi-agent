from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from travel_comparator.agents.auth import worker_auth_dependency
from travel_comparator.agents.common import A2AService
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import ErrorEnvelope

logger = logging.getLogger(__name__)


def create_worker_app(
    settings: Settings,
    audience: str,
    service: A2AService,
    service_url: str,
) -> FastAPI:
    settings.validate_for("weather" if audience == settings.weather_a2a_audience else "travel")
    auth = worker_auth_dependency(settings, audience)
    app = FastAPI(title=service.name, version="1.0.0", docs_url=None, redoc_url=None)

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "alive"}

    @app.get("/.well-known/agent-card.json", dependencies=[Depends(auth)])
    async def agent_card() -> dict[str, Any]:
        return service.agent_card(service_url)

    @app.post("/", dependencies=[Depends(auth)])
    async def json_rpc(request: Request) -> JSONResponse:
        correlation_id = request.headers.get("x-correlation-id", "unknown")
        request_id = None
        try:
            raw_body = bytearray()
            async for chunk in request.stream():
                raw_body.extend(chunk)
                if len(raw_body) > 32_768:
                    return JSONResponse(
                        status_code=413,
                        content=ErrorEnvelope(
                            code="REQUEST_TOO_LARGE",
                            source=service.name,
                            retryable=False,
                            correlation_id=correlation_id,
                        ).model_dump(mode="json"),
                    )
            payload = json.loads(raw_body)
            request_id = payload.get("id")
            if payload.get("jsonrpc") != "2.0" or payload.get("method") != "message/send":
                raise ValueError("Unsupported A2A request.")
            message = payload.get("params", {}).get("message", {})
            parts = message.get("parts", [])
            task_data = next(
                (part.get("data") for part in parts if part.get("mediaType") == "application/json"),
                None,
            )
            if not isinstance(task_data, dict):
                raise ValueError("Missing structured A2A task.")
            response = await service.send(task_data)
            body = {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {
                    "id": task_data.get("task_id"),
                    "status": {
                        "state": "completed" if response["status"] == "completed" else "failed"
                    },
                    "artifacts": [
                        {
                            "parts": [
                                {
                                    "data": response,
                                    "mediaType": "application/json",
                                }
                            ]
                        }
                    ],
                },
            }
            return JSONResponse(body)
        except (ValidationError, ValueError):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid A2A request",
                        "data": ErrorEnvelope(
                            code="A2A_INVALID_REQUEST",
                            source=service.name,
                            retryable=False,
                            correlation_id=correlation_id,
                        ).model_dump(mode="json"),
                    },
                },
                status_code=400,
            )
        except Exception as exc:
            logger.info(
                "worker request failed service=%s category=%s",
                service.name,
                type(exc).__name__,
            )
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32603,
                        "message": "Internal error",
                        "data": ErrorEnvelope(
                            code="A2A_INTERNAL_ERROR",
                            source=service.name,
                            retryable=False,
                            correlation_id=correlation_id,
                        ).model_dump(mode="json"),
                    },
                },
                status_code=500,
            )

    @app.exception_handler(HTTPException)
    async def auth_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.detail, headers=exc.headers)

    return app
