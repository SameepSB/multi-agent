from __future__ import annotations

from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from travel_comparator.config import Settings
from travel_comparator.contracts.v1 import ErrorEnvelope


def _unauthorized(correlation_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=ErrorEnvelope(
            code="WORKER_UNAUTHORIZED",
            source="worker_auth",
            retryable=False,
            correlation_id=correlation_id,
        ).model_dump(mode="json"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def worker_auth_dependency(settings: Settings, audience: str):
    async def verify(request: Request) -> dict[str, Any]:
        correlation_id = request.headers.get("x-correlation-id", "unknown")
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise _unauthorized(correlation_id)
        token = authorization[7:]
        if settings.app_env == "local":
            secret = settings.local_coordinator_token
            if secret is None or not _safe_match(token, secret.get_secret_value()):
                raise _unauthorized(correlation_id)
            return {"sub": "local-coordinator"}
        try:
            if not settings.oidc_jwks_url or not settings.oidc_issuer:
                raise ValueError("Missing worker OIDC settings.")
            signing_key = PyJWKClient(settings.oidc_jwks_url, timeout=3).get_signing_key_from_jwt(
                token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=settings.oidc_issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
                leeway=30,
            )
            if settings.trusted_coordinator_object_id != claims.get("oid"):
                raise ValueError("Untrusted coordinator identity.")
            roles = claims.get("roles")
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                raise ValueError("Invalid roles claim.")
            if "invoke" not in roles:
                raise ValueError("Missing invoke role.")
            return claims
        except Exception as exc:
            raise _unauthorized(correlation_id) from exc

    return verify


def _safe_match(candidate: str, secret: str) -> bool:
    import secrets

    return secrets.compare_digest(candidate.encode(), secret.encode())
