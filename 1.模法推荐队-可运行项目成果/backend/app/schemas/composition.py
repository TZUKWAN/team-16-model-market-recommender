"""Schema for model composition / orchestration."""

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class CompositionNode(BaseModel):
    """A single node in a composition flow."""
    node_id: str = ""
    step_order: int = 0
    capability: str = ""
    model_id: str = ""
    model_name: str = ""
    source: Literal["official", "demo"] = "official"
    catalog_version: str = ""
    input_requirements: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    fit_score: float = 0.0
    node_explanation: str = ""
    # DAG dependency: which upstream node ids this node depends on. Empty for
    # source nodes. Populated from explicit template edges so the flow is a real
    # DAG rather than an implicit linear chain.
    depends_on: list[str] = Field(default_factory=list)
    # Whether missing IO is a hard blocker (fails the flow) or soft (degrades).
    # Defaults to "soft"; set to "hard" when the node's core input is missing.
    dependency_type: str = "soft"


class CompositionEdge(BaseModel):
    """An edge connecting two composition nodes."""
    source_node_id: str = ""
    target_node_id: str = ""
    io_status: str = ""  # pass / partial / fail
    missing_fields: list[str] = Field(default_factory=list)
    suggestion: str = ""


class IOCompatibilityResult(BaseModel):
    """Overall IO compatibility check result."""
    total_edges: int = 0
    passed: int = 0
    partial: int = 0
    failed: int = 0
    compatibility_rate: float = 0.0


class CompositionExecutionNode(BaseModel):
    """Execution-state view for a composition node."""
    node_id: str = ""
    step_order: int = 0
    model_id: str = ""
    model_name: str = ""
    capability: str = ""
    # Execution state machine: pending / running / completed / degraded /
    # failed / blocked. "blocked" means an upstream hard dependency failed so
    # this node cannot run; "degraded" means soft inputs are missing but the
    # node still produced output.
    status: str = "pending"
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    output_snapshot: dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    elapsed_ms: int = 0
    demo_data: bool = True
    desensitized_notice: str = ""
    # Provenance: for each consumed field, which upstream node produced it.
    # Empty for source nodes or fields coming from external data.
    input_lineage: dict[str, str] = Field(default_factory=dict)
    # Why this node is degraded/blocked/failed, if applicable.
    status_reason: str = ""


class CompositionExecutionEdge(BaseModel):
    """Execution-state view for a composition edge."""
    source_node_id: str = ""
    target_node_id: str = ""
    status: str = "pending"
    transferred_fields: list[str] = Field(default_factory=list)
    note: str = ""


class CompositionExecutionResult(BaseModel):
    """Demo execution result for a composition flow."""
    execution_id: str = ""
    status: str = "pending"
    demo_data: bool = True
    desensitized_notice: str = ""
    nodes: list[CompositionExecutionNode] = Field(default_factory=list)
    edges: list[CompositionExecutionEdge] = Field(default_factory=list)
    fused_result: dict[str, Any] = Field(default_factory=dict)
    # Result lineage: which node contributed each field in the fused result,
    # so the final output is traceable to its producing node.
    node_contributions: list[dict[str, Any]] = Field(default_factory=list)


class RecommendCompositionRequest(BaseModel):
    """Request for composition recommendation."""

    model_config = ConfigDict(extra="forbid")

    parse_result: dict[str, Any] = Field(default_factory=dict, description="需求解析结果")
    model_source: Literal["official", "demo"] = Field(
        default="official",
        description="候选模型目录；生产默认仅使用官方目录，demo 必须显式指定",
    )
    top_k: int = Field(default=3, ge=1, le=10, description="每个节点候选模型数")


class RecommendCompositionResponse(BaseModel):
    """Response containing the recommended composition."""
    composition_id: str = ""
    composition_name: str = ""
    scenario: str = ""
    total_score: float = 0.0
    composition_status: str = "ready"
    failure_reasons: list[str] = Field(default_factory=list)
    demo_execution_only: bool = True
    nodes: list[CompositionNode] = Field(default_factory=list)
    flow_edges: list[CompositionEdge] = Field(default_factory=list)
    io_compatibility: IOCompatibilityResult = Field(default_factory=IOCompatibilityResult)
    missing_data: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    business_explanation: str = ""
    technical_explanation: str = ""
    management_explanation: str = ""
    usage_guide: list[str] = Field(default_factory=list)
    execution_result: CompositionExecutionResult | None = None
