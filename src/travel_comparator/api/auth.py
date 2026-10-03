from __future__ import annotations

import secrets
from typing import Any

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWKClient

from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import ErrorEnvelope


def api_auth_dependency(settings: Settings):
    async def authenticate(request: Request) -> dict[str, Any]:
        correlation_id = request.state.correlation_id
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise _unauthorized(correlation_id)
        token = authorization[7:]
        if settings.app_env == "local":
            expected = settings.local_api_token
            if expected is None or not secrets.compare_digest(
                token.encode(), expected.get_secret_value().encode()
            ):
                raise _unauthorized(correlation_id)
            return {"sub": "local-user", "roles": ["TravelComparator.User"]}
        try:
            if not settings.oidc_jwks_url or not settings.oidc_issuer or not settings.oidc_audience:
                raise ValueError("OIDC is not configured.")
            signing_key = PyJWKClient(settings.oidc_jwks_url, timeout=3).get_signing_key_from_jwt(
                token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.oidc_audience,
                issuer=settings.oidc_issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
                leeway=30,
            )
            roles = claims.get("roles")
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                raise ValueError("Invalid roles claim.")
            if "TravelComparator.User" not in roles:
                raise ValueError("Required application role is absent.")
            return claims
        except Exception as exc:
            raise _unauthorized(correlation_id) from exc

    return authenticate


def _unauthorized(correlation_id: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=ErrorEnvelope(
            code="UNAUTHORIZED",
            source="api_auth",
            retryable=False,
            correlation_id=correlation_id,
        ).model_dump(mode="json"),
        headers={"WWW-Authenticate": "Bearer"},
    )
