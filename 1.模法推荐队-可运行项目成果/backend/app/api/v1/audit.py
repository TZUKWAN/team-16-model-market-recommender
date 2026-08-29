"""Audit log query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.schemas.audit import AuditEventsResponse
from app.schemas.auth import UserContext
from app.services.audit_service import get_audit_service

router = APIRouter()


@router.get("/audit/events", response_model=AuditEventsResponse)
async def list_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    """List recent audit events for authorized audit viewers."""
    if not current_user.can_view_audit:
        raise HTTPException(status_code=403, detail="当前用户无审计日志查看权限")

    events = get_audit_service().query(
        limit=limit,
        event_type=event_type,
        user_id=user_id,
    )
    return AuditEventsResponse(total=len(events), events=events)
