from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from travel_comparator.agents.common import A2AService
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import A2ATaskRequest, WeatherObservation


class MCPToolError(RuntimeError):
    def __init__(self, retryable: bool = False) -> None:
        super().__init__("Weather tool call failed.")
        self.retryable = retryable


class MCPWeatherClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def assess(self, destination: str, timeout: float) -> dict[str, Any]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        environment.update(
            {
                "APP_ENV": self._settings.app_env,
                "LOG_LEVEL": self._settings.log_level,
                "REQUEST_TIMEOUT_SECONDS": str(self._settings.request_timeout_seconds),
                "MAX_CITIES": str(self._settings.max_cities),
                "STUB_PROVIDERS": str(self._settings.stub_providers).lower(),
                "TRAVEL_DATA_PATH": str(Path(self._settings.travel_data_path).resolve()),
            }
        )
        if self._settings.nws_user_agent:
            environment["NWS_USER_AGENT"] = self._settings.nws_user_agent
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "travel_comparator.providers.nws.mcp_server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )

        async def send(request_id: int, method: str, params: dict[str, Any] | None = None) -> dict:
            assert process.stdin and process.stdout
            message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
            if params is not None:
                message["params"] = params
            process.stdin.write((json.dumps(message) + "\n").encode())
            await process.stdin.drain()
            line = await process.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed its output.")
            response = json.loads(line)
            if response.get("error"):
                raise MCPToolError(bool(response["error"].get("data", {}).get("retryable")))
            return response.get("result", {})

        try:
            async with asyncio.timeout(timeout):
                await send(1, "initialize", {"protocolVersion": "2026-07-28"})
                assert process.stdin
                process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                await process.stdin.drain()
                tools = await send(2, "tools/list")
                allowed = [
                    tool
                    for tool in tools.get("tools", [])
                    if tool.get("name") == "get_weather_assessment"
                ]
                if len(allowed) != 1:
                    raise RuntimeError("MCP tool capability is unavailable.")
                result = await send(
                    3,
                    "tools/call",
                    {
                        "name": "get_weather_assessment",
                        "arguments": {"destination": destination},
                    },
                )
                data = result["content"][0]["text"]
                parsed = WeatherObservation.model_validate(json.loads(data))
                return parsed.model_dump(mode="json")
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except TimeoutError:
                    process.kill()
                    await process.wait()


def create_service(settings: Settings) -> A2AService:
    client = MCPWeatherClient(settings)

    async def handle(task: A2ATaskRequest) -> dict[str, Any]:
        destination = task.payload.get("destination")
        if not isinstance(destination, str) or len(destination) > 80:
            raise ValueError("Invalid destination.")
        return await client.assess(destination, task.deadline_seconds)

    return A2AService(
        name="Travel Comparator Weather Agent",
        description="Weather assessment through an allow-listed private MCP stdio process.",
        skills=[
            {
                "id": "assess_weather",
                "name": "Weather Assessment",
                "description": "Assess forecast and active NWS alerts for a supported destination.",
            }
        ],
        expected_action="assess_weather",
        handler=handle,
    )
