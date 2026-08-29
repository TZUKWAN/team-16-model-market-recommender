"""FastAPI security dependencies for local demo access control."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.schemas.auth import UserContext
from app.core.config import get_settings
from app.services.auth_service import (
    AuthConfigurationError,
    AuthenticationError,
    EnterpriseJWTAdapter,
    get_auth_service,
)


async def get_current_user(
    x_user_id: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> UserContext:
    """Resolve the current local user from request headers."""
    settings = get_settings()
    if settings.AUTH_MODE == "demo":
        return get_auth_service().get_user(x_user_id)
    if settings.AUTH_MODE != "real":
        raise HTTPException(status_code=503, detail="invalid AUTH_MODE configuration")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return EnterpriseJWTAdapter(settings).authenticate(token)
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=f"invalid bearer token: {exc}") from exc
