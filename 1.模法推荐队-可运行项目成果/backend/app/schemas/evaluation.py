"""
Schemas for evaluation metrics.
Corresponds to GET /api/v1/evaluation/metrics
"""

from pydantic import BaseModel, Field


class MetricDetail(BaseModel):
    """Detailed breakdown of a single metric."""

    name: str = Field(default="", description="Metric name")
    value: float = Field(default=0.0, description="Metric value")
    target: float = Field(default=0.0, description="Target value")
    unit: str = Field(default="", description="Unit of measurement")
    is_met: bool = Field(default=False, description="Whether the metric meets the target")
    sample_count: int = Field(default=0, description="Number of test samples for this metric")


class EvaluationMetricsResponse(BaseModel):
    """Overall evaluation metrics for the system."""

    metrics: list[MetricDetail] = Field(default_factory=list, description="Detailed metrics array")
    overall_score: float = Field(default=0.0, description="Overall weighted score")
    report_generated_at: str = Field(default="", description="ISO-8601 timestamp of report generation")
    is_mock: bool = Field(default=True, description="Whether the metrics are from mock/demo data")
    total_models_covered: int = Field(default=0, description="Number of models covered in evaluation")
    total_samples: int = Field(default=0, description="Total number of test samples")


# Kept for backward compatibility in imports
class ScenarioMetric(BaseModel):
    """Metrics for a specific business scenario."""

    scenario: str = Field(default="", description="Scenario name")
    intent_accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Intent identification accuracy")
    tag_conversion_accuracy: float = Field(default=0.0, ge=0.0, le=1.0, description="Tag conversion accuracy")
    top3_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Top-3 recommendation hit rate")
    top5_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Top-5 recommendation hit rate")
    composition_fitness: float = Field(default=0.0, ge=0.0, le=1.0, description="Composition model fitness")
    sample_count: int = Field(default=0, description="Number of test samples for this scenario")
