"""Schemas for local role and institution access control."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Authenticated local user context."""

    user_id: str = ""
    display_name: str = ""
    role: str = ""
    institution_id: str = ""
    legal_entity_id: str = ""
    permitted_domains: list[str] = Field(default_factory=list)
    can_recommend: bool = True
    can_invoke_models: bool = True
    can_view_results: bool = True
    can_view_audit: bool = False


class TaskAccessContext(BaseModel):
    """Access context bound to an invocation task."""

    task_id: str = ""
    model_id: str = ""
    user_id: str = ""
    institution_id: str = ""
    legal_entity_id: str = ""
