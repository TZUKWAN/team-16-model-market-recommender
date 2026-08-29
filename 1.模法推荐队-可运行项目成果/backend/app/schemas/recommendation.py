"""Schema for model recommendation."""

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class ScoreBreakdown(BaseModel):
    """Multi-dimensional score breakdown."""
    scenario_match: float = 0.0
    customer_match: float = 0.0
    data_match: float = 0.0
    output_match: float = 0.0
    graph_path_match: float = 0.0
    field_compatibility: float = 0.0
    hybrid_retrieval_match: float = 0.0
    llm_semantic_match: float = 0.0
    performance: float = 0.0
    landing_experience: float = 0.0
    compliance: float = 0.0


class EvidenceCard(BaseModel):
    """A single evidence item supporting the recommendation."""
    evidence_type: str = ""
    content: str = ""
    source: str = ""
    evidence_text: str = ""
    source_field: str = ""
    confidence: float = 0.0


class AlternativeModel(BaseModel):
    """Alternative model information."""
    model_id: str = ""
    model_name: str = ""
    reason: str = ""


class DataReadinessReport(BaseModel):
    """Data readiness diagnosis for a recommended model."""
    readiness_score: float = 0.0
    required_fields: list[str] = Field(default_factory=list)
    available_fields: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    missing_optional_fields: list[str] = Field(default_factory=list)
    confidence_impact: str = ""
    action_items: list[str] = Field(default_factory=list)
    substitution_notes: list[str] = Field(default_factory=list)


class RecommendedModel(BaseModel):
    """A single recommended model with full detail."""
    model_id: str = ""
    model_name: str = ""
    source: str = ""
    catalog_version: str = ""
    rank: int = 0
    total_score: float = 0.0
    rule_score: float = 0.0
    graph_score: float = 0.0
    retrieval_score: float = 0.0
    llm_score: float = 0.0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    recommendation_reason: str = ""
    evidence_cards: list[EvidenceCard] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    applicable_boundary: str = ""
    unsuitable_conditions: str = ""
    compliance_notes: str = ""
    alternative_models: list[AlternativeModel] = Field(default_factory=list)
    data_readiness: DataReadinessReport = Field(default_factory=DataReadinessReport)


class UnrecommendedExample(BaseModel):
    """Example of a model that was not recommended and why."""
    model_id: str = ""
    model_name: str = ""
    reason: str = ""


class RecommendModelsRequest(BaseModel):
    """Request for model recommendation."""

    model_config = ConfigDict(extra="forbid")

    parse_result: dict[str, Any] = Field(description="需求解析结果")
    model_source: Literal["official", "demo", "official_then_demo"] = Field(
        default="official_then_demo",
        description="候选模型策略；默认返回官方主榜，并附带独立标注的 demo 参考候选",
    )
    top_k: int = Field(default=5, ge=1, le=20, description="返回推荐数量")
    demo_top_k: int = Field(
        default=3,
        ge=0,
        le=10,
        description="official_then_demo 策略下附带的 demo 参考候选数量",
    )
    prefer_api_available: bool = Field(default=False, description="是否优先推荐可 API 调用的模型")
    prefer_landing_cases: bool = Field(default=False, description="是否优先推荐有落地案例的模型")
    client_request_id: str = Field(
        default="",
        max_length=128,
        description="客户端幂等键；同一请求重试时保持不变",
    )


class RecommendModelsResponse(BaseModel):
    """Response containing model recommendations."""
    request_id: str = ""
    recommendations: list[RecommendedModel] = Field(default_factory=list)
    demo_references: list[RecommendedModel] = Field(default_factory=list)
    unrecommended_examples: list[UnrecommendedExample] = Field(default_factory=list)
    summary: str = ""
    catalog_policy: Literal["official", "demo", "official_then_demo"] = "official"
    demo_reference_status: Literal["not_requested", "available", "unavailable"] = "not_requested"
    official_recommendation_count: int = 0
    demo_reference_count: int = 0
    version_id: str = ""
    version_number: int = 0
