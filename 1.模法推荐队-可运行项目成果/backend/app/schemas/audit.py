"""Schemas for audit log events."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """A single append-only audit event."""

    event_id: str = ""
    event_type: str = ""
    timestamp: str = ""
    user_id: str = ""
    role: str = ""
    institution_id: str = ""
    legal_entity_id: str = ""
    request_id: str = ""
    model_id: str = ""
    task_id: str = ""
    result_type: str = ""
    status: str = "success"
    payload_summary: dict[str, Any] = Field(default_factory=dict)


class AuditEventsResponse(BaseModel):
    """Audit query response."""

    total: int = 0
    events: list[AuditEvent] = Field(default_factory=list)
