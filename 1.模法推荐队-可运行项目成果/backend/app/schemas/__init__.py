"""Unified schemas for the Model Market Assistant API."""

from .demand import ClarificationQuestion, ParseDemandRequest, ParseDemandResponse
from .model import ModelMetadata
from .recommendation import (
    ScoreBreakdown,
    DataReadinessReport,
    EvidenceCard,
    AlternativeModel,
    RecommendedModel,
    UnrecommendedExample,
    RecommendModelsRequest,
    RecommendModelsResponse,
)
from .composition import (
    CompositionNode,
    CompositionEdge,
    CompositionExecutionEdge,
    CompositionExecutionNode,
    CompositionExecutionResult,
    IOCompatibilityResult,
    RecommendCompositionRequest,
    RecommendCompositionResponse,
)
from .report import ReportRequest, ReportResponse, ReportSection
from .evaluation import EvaluationMetricsResponse, ScenarioMetric, MetricDetail
from .knowledge_graph import (
    GraphEdge,
    GraphMatchPathRequest,
    GraphMatchPathResponse,
    GraphNeighborhood,
    GraphNode,
    GraphOverview,
    KnowledgeGraphSnapshot,
)
from .inference import (
    ModelInvokeRequest,
    ModelInvokeResponse,
    ModelResultResponse,
    ModelResultSchemaResponse,
    ModelTaskStatusResponse,
)
from .auth import TaskAccessContext, UserContext
from .audit import AuditEvent, AuditEventsResponse

__all__ = [
    "ParseDemandRequest",
    "ParseDemandResponse",
    "ClarificationQuestion",
    "ModelMetadata",
    "ScoreBreakdown",
    "DataReadinessReport",
    "EvidenceCard",
    "AlternativeModel",
    "RecommendedModel",
    "UnrecommendedExample",
    "RecommendModelsRequest",
    "RecommendModelsResponse",
    "CompositionNode",
    "CompositionEdge",
    "CompositionExecutionEdge",
    "CompositionExecutionNode",
    "CompositionExecutionResult",
    "IOCompatibilityResult",
    "RecommendCompositionRequest",
    "RecommendCompositionResponse",
    "ReportRequest",
    "ReportResponse",
    "ReportSection",
    "EvaluationMetricsResponse",
    "ScenarioMetric",
    "MetricDetail",
    "GraphNode",
    "GraphEdge",
    "GraphOverview",
    "GraphNeighborhood",
    "GraphMatchPathRequest",
    "GraphMatchPathResponse",
    "KnowledgeGraphSnapshot",
    "ModelInvokeRequest",
    "ModelInvokeResponse",
    "ModelTaskStatusResponse",
    "ModelResultResponse",
    "ModelResultSchemaResponse",
    "TaskAccessContext",
    "UserContext",
    "AuditEvent",
    "AuditEventsResponse",
]
