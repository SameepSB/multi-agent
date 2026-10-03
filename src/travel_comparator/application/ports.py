from __future__ import annotations

from typing import Protocol

from travel_comparator.contracts.v1 import TripRequest


class AgentPort(Protocol):
    async def weather(self, destination: str, correlation_id: str, deadline: float) -> dict: ...

    async def travel(
        self,
        action: str,
        request: TripRequest,
        correlation_id: str,
        deadline: float,
        constraints: list[dict] | None = None,
    ) -> dict: ...
