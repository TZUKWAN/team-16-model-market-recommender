"""Schemas for recommendation feedback and adoption stats."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

FeedbackAction = Literal["recommended", "adopt", "reject", "favorite"]
EvidenceMode = Literal["human", "demo", "test"]


class FeedbackRequest(BaseModel):
    """User feedback for a recommended model."""

    request_id: str = ""
    model_id: str
    model_name: str = ""
    action: Literal["adopt", "reject", "favorite"]
    reason: str = ""
    scenario: str = ""
    parse_result: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_mode: EvidenceMode = "human"


class FeedbackEvent(BaseModel):
    """Append-only feedback event."""

    event_id: str = ""
    timestamp: str = ""
    user_id: str = ""
    role: str = ""
    institution_id: str = ""
    request_id: str = ""
    model_id: str = ""
    model_name: str = ""
    scenario: str = ""
    action: FeedbackAction
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_mode: EvidenceMode = "human"


class FeedbackResponse(BaseModel):
    """Feedback write response."""

    event_id: str
    status: str = "recorded"


class ModelFeedbackStats(BaseModel):
    """Aggregated feedback stats for one model/scenario bucket."""

    model_id: str = ""
    model_name: str = ""
    scenario: str = ""
    recommended_count: int = 0
    adopt_count: int = 0
    reject_count: int = 0
    favorite_count: int = 0
    adoption_rate: float = 0.0


class FeedbackStatsResponse(BaseModel):
    """Feedback stats response."""

    total_events: int = 0
    items: list[ModelFeedbackStats] = Field(default_factory=list)
    human_event_count: int = 0
    demo_event_count: int = 0
    test_event_count: int = 0