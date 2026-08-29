"""Recommendation feedback endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.security import get_current_user
from app.schemas.auth import UserContext
from app.schemas.feedback import FeedbackRequest, FeedbackResponse, FeedbackStatsResponse
from app.services.feedback_service import get_feedback_service

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def record_feedback(
    request: FeedbackRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Record explicit adopt/reject/favorite feedback for a recommendation."""
    scenario = request.scenario or str(
        request.parse_result.get("business_scenario")
        or request.parse_result.get("intent")
        or "unknown"
    )
    event = get_feedback_service().record_feedback(
        current_user,
        request_id=request.request_id,
        model_id=request.model_id,
        model_name=request.model_name,
        action=request.action,
        reason=request.reason,
        scenario=scenario,
        metadata=request.metadata,
        evidence_mode=request.evidence_mode,
    )
    return FeedbackResponse(event_id=event.event_id)


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def feedback_stats(
    scenario: str = Query(default=""),
    role: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    evidence_mode: str = Query(default=""),
    current_user: UserContext = Depends(get_current_user),
):
    """Return model adoption stats grouped by model and scenario."""
    effective_role = role if current_user.can_view_audit else (role or current_user.role)
    service = get_feedback_service()
    items, mode_counts = service.stats(
        scenario=scenario, role=effective_role, limit=limit, evidence_mode=evidence_mode
    )
    return FeedbackStatsResponse(
        total_events=service.total_events(),
        items=items,
        human_event_count=mode_counts.get("human", 0),
        demo_event_count=mode_counts.get("demo", 0),
        test_event_count=mode_counts.get("test", 0),
    )