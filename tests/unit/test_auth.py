from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from travel_comparator.agents.auth import worker_auth_dependency
from travel_comparator.api.auth import api_auth_dependency


def _request(authorization: str) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"authorization", authorization.encode())],
            "query_string": b"",
            "server": ("localhost", 80),
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
        }
    )
    request.state.correlation_id = "test-correlation"
    return request


def _configure_oidc(settings) -> None:
    settings.app_env = "production"
    settings.oidc_issuer = "https://issuer.example/"
    settings.oidc_jwks_url = "https://issuer.example/keys"
    settings.oidc_audience = "travel-api"
    settings.weather_a2a_audience = "weather-agent"
    settings.trusted_coordinator_object_id = "coordinator-object-id"


def _stub_signing(monkeypatch, claims: dict) -> None:
    from travel_comparator.agents import auth as worker_auth
    from travel_comparator.api import auth as api_auth

    client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(key="test-key")
    )
    monkeypatch.setattr(worker_auth, "PyJWKClient", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(api_auth, "PyJWKClient", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(worker_auth.jwt, "decode", lambda *_args, **_kwargs: claims)


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ["TravelComparator.User", ["another-role"]])
async def test_api_rejects_missing_or_malformed_roles(settings, monkeypatch, roles):
    _configure_oidc(settings)
    claims = {"sub": "user-1", "roles": roles}
    _stub_signing(monkeypatch, claims)

    with pytest.raises(HTTPException) as error:
        await api_auth_dependency(settings)(_request("Bearer signed-token"))

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_api_accepts_required_role_in_role_list(settings, monkeypatch):
    _configure_oidc(settings)
    claims = {"sub": "user-1", "roles": ["TravelComparator.User"]}
    _stub_signing(monkeypatch, claims)

    authenticated = await api_auth_dependency(settings)(_request("Bearer signed-token"))

    assert authenticated is claims


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", ["invoke", ["not-invoke"]])
async def test_worker_rejects_missing_or_malformed_roles(settings, monkeypatch, roles):
    _configure_oidc(settings)
    claims = {
        "oid": "coordinator-object-id",
        "roles": roles,
    }
    _stub_signing(monkeypatch, claims)

    with pytest.raises(HTTPException) as error:
        await worker_auth_dependency(settings, "weather-agent")(_request("Bearer signed-token"))

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_worker_accepts_trusted_coordinator_role_list(settings, monkeypatch):
    _configure_oidc(settings)
    claims = {
        "oid": "coordinator-object-id",
        "roles": ["invoke"],
    }
    _stub_signing(monkeypatch, claims)

    authenticated = await worker_auth_dependency(settings, "weather-agent")(
        _request("Bearer signed-token")
    )

    assert authenticated is claims
