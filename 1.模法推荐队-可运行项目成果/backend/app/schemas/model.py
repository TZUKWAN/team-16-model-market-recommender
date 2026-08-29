"""Schema for model metadata."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class ModelMetadata(BaseModel):
    """Full metadata for a single model."""
    model_id: str = ""
    model_name: str = ""
    domain: str = ""
    business_scenario: list[str] = Field(default_factory=list)
    business_stage: list[str] = Field(default_factory=list)
    customer_segment: list[str] = Field(default_factory=list)
    model_capability: list[str] = Field(default_factory=list)
    input_fields_required: list[str] = Field(default_factory=list)
    input_fields_optional: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    performance_metrics: dict[str, Any] = Field(default_factory=dict)
    applicable_conditions: str = ""
    unsuitable_conditions: str = ""
    compliance_boundary: str = ""
    deployment_status: str = "mock_available"
    api_available: bool = False
    historical_cases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    canonical_name: str = ""
    aliases: list[str] = Field(default_factory=list)
    source: str = "demo"
    catalog_version: str = "demo-v1"
    asset_version: str = "1.0.0"
    asset_status: str = "cataloged"
    permission_scope: str = "demo_desensitized"
    legal_boundary: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    result_schema: dict[str, Any] = Field(default_factory=dict)
    total_questions: int = 0
    field_provenance: dict[str, dict[str, str]] = Field(default_factory=dict)
