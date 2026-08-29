"""Recommendation version history and diff endpoints (F5.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.core.logging import get_logger
from app.schemas.auth import UserContext
from app.services.recommendation_version_store import get_recommendation_version_store

router = APIRouter()
logger = get_logger(__name__)


def _access_scope(user: UserContext) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "institution_id": user.institution_id,
        "legal_entity_id": user.legal_entity_id,
        "can_view_audit": user.can_view_audit,
    }


@router.get("/recommendation-versions/{session_id}")
async def list_versions(
    session_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """List all persisted recommendation versions for a session."""
    store = get_recommendation_version_store()
    versions = store.list_versions(session_id, **_access_scope(current_user))
    logger.info(f"Listed {len(versions)} versions for session {session_id}")
    return {"session_id": session_id, "versions": versions, "count": len(versions)}


@router.get("/recommendation-versions/{session_id}/diff")
async def diff_versions(
    session_id: str,
    version_a: str = Query(...),
    version_b: str = Query(...),
    current_user: UserContext = Depends(get_current_user),
):
    """Compare two recommendation versions visible to the current user."""
    store = get_recommendation_version_store()
    diff = store.diff_versions(
        session_id,
        version_a,
        version_b,
        **_access_scope(current_user),
    )
    if diff.get("error"):
        raise HTTPException(status_code=404, detail="推荐版本不存在或当前用户无权访问")
    return diff


@router.get("/recommendation-versions/{session_id}/{version_id}")
async def get_version(
    session_id: str,
    version_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get a single recommendation version visible to the current user."""
    store = get_recommendation_version_store()
    version = store.get_version(
        session_id,
        version_id,
        **_access_scope(current_user),
    )
    if version is None:
        raise HTTPException(status_code=404, detail="推荐版本不存在或当前用户无权访问")
    return version
