"""Schemas for model comparison and effect estimation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.recommendation import DataReadinessReport

MetricSource = Literal["verified", "draft", "missing"]
EvidenceLevel = Literal["high", "medium", "low"]


class EffectEstimate(BaseModel):
    """Transparent non-production estimate for expected business effect."""

    estimated_lift_pct: float = 0.0
    coverage_pct: float = 0.0
    confidence_band_pct: list[float] = Field(default_factory=list)
    data_readiness_factor: float = 0.0
    segment_match_factor: float = 0.0
    basis: list[str] = Field(default_factory=list)
    disclaimer: str = "基于模型历史指标与数据就绪度的预估值，非真实模型调用结果。"
    metric_source: MetricSource = "missing"
    verification_status: str = "未验证"
    evidence_level: EvidenceLevel = "low"
    assumptions: list[str] = Field(default_factory=list)
    not_for_decision: bool = True


class ModelComparisonItem(BaseModel):
    """One model column in the comparison matrix."""

    model_id: str = ""
    model_name: str = ""
    domain: str = ""
    customer_segment: list[str] = Field(default_factory=list)
    input_fields_required: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    performance_metrics: dict[str, Any] = Field(default_factory=dict)
    applicable_conditions: str = ""
    unsuitable_conditions: str = ""
    compliance_boundary: str = ""
    data_readiness: DataReadinessReport = Field(default_factory=DataReadinessReport)
    effect_estimate: EffectEstimate = Field(default_factory=EffectEstimate)


class CompareModelsRequest(BaseModel):
    """Request to compare selected models side by side."""

    model_ids: list[str] = Field(default_factory=list, min_length=2, max_length=5)
    parse_result: dict[str, Any] = Field(default_factory=dict)


class CompareModelsResponse(BaseModel):
    """Structured comparison matrix plus per-model effect estimates."""

    request_id: str = ""
    items: list[ModelComparisonItem] = Field(default_factory=list)
    matrix: list[dict[str, Any]] = Field(default_factory=list)
    disclaimer: str = "效果预估基于历史指标、数据就绪度和客群匹配折算，非真实调用或生产验收结果。"