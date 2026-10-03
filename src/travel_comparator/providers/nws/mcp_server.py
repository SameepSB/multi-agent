"""Minimal MCP stdio server with explicit tools and allow-listed NWS access."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from travel_comparator.config import Settings
from travel_comparator.providers.nws.client import WeatherProvider


async def serve() -> None:
    settings = Settings()
    data = json.loads(Path(settings.travel_data_path).read_text(encoding="utf-8"))
    provider = WeatherProvider(settings.stub_providers, data, settings.nws_user_agent)
    for line in sys.stdin:
        request_id = None
        try:
            message = json.loads(line)
            method = message.get("method")
            request_id = message.get("id")
            if method == "initialize":
                result = {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "travel-weather-tools", "version": "1.0.0"},
                }
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "get_weather_assessment",
                            "description": (
                                "Assess weather for a configured supported US destination."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "destination": {"type": "string"},
                                    "departure_date": {
                                        "type": ["string", "null"],
                                        "format": "date",
                                    },
                                },
                                "required": ["destination"],
                                "additionalProperties": False,
                            },
                        }
                    ]
                }
            elif method == "tools/call":
                params = message.get("params", {})
                if params.get("name") != "get_weather_assessment":
                    raise ValueError("Tool is not allow-listed.")
                arguments = params.get("arguments", {})
                if (
                    not isinstance(arguments, dict)
                    or not {"destination"}.issubset(arguments)
                    or set(arguments) - {"destination", "departure_date"}
                ):
                    raise ValueError("Invalid tool arguments.")
                raw_departure_date = arguments["departure_date"]
                if raw_departure_date is not None and not isinstance(raw_departure_date, str):
                    raise ValueError("Invalid departure date.")
                departure_date = (
                    date.fromisoformat(raw_departure_date) if raw_departure_date else None
                )
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                await provider.assess(arguments["destination"], departure_date)
                            ),
                        }
                    ],
                    "isError": False,
                }
            elif method == "notifications/initialized":
                continue
            else:
                raise ValueError("Unsupported MCP method.")
            if request_id is not None:
                print(
                    json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}), flush=True
                )
        except Exception as exc:
            if "request_id" in locals() and request_id is not None:
                print(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32000,
                                "message": type(exc).__name__,
                                "data": {"retryable": bool(getattr(exc, "retryable", False))},
                            },
                        }
                    ),
                    flush=True,
                )


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
