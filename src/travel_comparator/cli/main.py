from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date
from pathlib import Path

from travel_comparator.application.a2a_client import A2AAgentClient
from travel_comparator.application.coordinator import Coordinator, NoUsableComparison
from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import TripRequest, contains_payment_data
from travel_comparator.providers.openai.client import OpenAIAdapter, parse_local_query


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    settings.validate_for("coordinator")
    if not args.request_json and contains_payment_data(args.query):
        raise ValueError("Query rejected by input safety policy.")
    data = json.loads(Path(settings.travel_data_path).read_text(encoding="utf-8"))
    client = A2AAgentClient(settings)
    openai = None
    if args.request_json:
        request = TripRequest.model_validate_json(args.request_json)
    elif settings.stub_providers:
        origin, destinations = parse_local_query(
            args.query,
            [city["name"] for city in data["cities"]],
            settings.max_cities,
        )
        duration = 5
        duration_match = re.search(r"\b(\d{1,2})\s*[- ]?day", args.query, re.I)
        if duration_match:
            duration = int(duration_match.group(1))
        departure_date = None
        if re.search(r"\bmid[- ]march\b", args.query, re.I):
            year = date.today().year + (date.today().month >= 3)
            departure_date = date(year, 3, 15)
        request = TripRequest(
            origin=origin,
            destinations=destinations,
            departure_date=departure_date,
            duration_days=duration,
        )
    else:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for natural-language query parsing.")
        openai = OpenAIAdapter(settings.openai_api_key.get_secret_value(), settings.openai_model)
        request = await openai.parse_query(args.query, settings.max_cities)
    if len(request.destinations) > settings.max_cities:
        raise ValueError("Destination count exceeds configured maximum.")
    coordinator = Coordinator(
        client,
        settings.request_timeout_seconds,
        narrative_provider=(None if settings.stub_providers or openai is None else openai.explain),
    )
    try:
        result = await coordinator.compare(request)
        print(result.model_dump_json(indent=2))
        return 0
    except NoUsableComparison as exc:
        print(json.dumps({"status": "failed", "message": str(exc)}), file=sys.stderr)
        return 2
    finally:
        await client.close()
        if openai:
            await openai.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="travel-comparator")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument(
        "--request-json",
        help="Canonical v1 request JSON (for automation; otherwise query is natural language).",
    )
    args = parser.parse_args()
    if not args.request_json and not args.query:
        parser.error("provide a natural-language query or --request-json")
    try:
        status = asyncio.run(run(args))
    except TimeoutError:
        print('{"status":"failed","error":"deadline_exceeded"}', file=sys.stderr)
        status = 124
    except Exception as exc:
        print(
            json.dumps({"status": "failed", "error": type(exc).__name__}),
            file=sys.stderr,
        )
        status = 2
    raise SystemExit(status)
