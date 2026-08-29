"""Schemas for model invocation and task/result retrieval."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelInvokeRequest(BaseModel):
    """Request payload for invoking a model."""

    input_data: dict[str, Any] = Field(default_factory=dict)
    async_mode: bool = False
    request_context: dict[str, Any] = Field(default_factory=dict)


class ModelInvokeResponse(BaseModel):
    """Response for model invocation."""

    model_id: str = ""
    task_id: str = ""
    status: str = ""
    demo_data: bool = False
    submitted_at: str = ""
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class ModelTaskStatusResponse(BaseModel):
    """Async model task status."""

    task_id: str = ""
    status: str = ""
    demo_data: bool = False
    updated_at: str = ""
    message: str = ""


class ModelResultResponse(BaseModel):
    """Async model task result."""

    task_id: str = ""
    status: str = ""
    demo_data: bool = False
    result: dict[str, Any] = Field(default_factory=dict)


class ModelResultSchemaResponse(BaseModel):
    """Model result schema response."""

    model_id: str = ""
    demo_data: bool = False
    result_schema: dict[str, Any] = Field(default_factory=dict)
