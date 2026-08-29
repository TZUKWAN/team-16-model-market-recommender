"""
Schemas for recommendation report generation.
Corresponds to POST /api/v1/reports/recommendation
"""

from pydantic import BaseModel, Field
from typing import Any


class ReportRequest(BaseModel):
    """Request for generating a recommendation report."""

    request_id: str = Field(default="", description="The original recommendation request ID")
    format: str = Field(default="markdown", description="Report format: markdown / html / pdf")
    include_details: bool = Field(default=True, description="Whether to include detailed evidence cards")
    demand_raw: str = Field(default="", description="Original user demand text")
    parse_result: dict[str, Any] = Field(default_factory=dict, description="Demand parsing result")
    recommend_result: dict[str, Any] = Field(default_factory=dict, description="Recommendation result")
    composition_result: dict[str, Any] = Field(default_factory=dict, description="Composition recommendation result")
    model_result: dict[str, Any] = Field(default_factory=dict, description="Model invocation result sample")
    recommendations: list[dict[str, Any]] = Field(default_factory=list, description="Recommendation list alias")
    composition: dict[str, Any] = Field(default_factory=dict, description="Composition result alias")


class ReportSection(BaseModel):
    """A section within the generated report."""

    title: str = Field(default="", description="Section title")
    content: str = Field(default="", description="Section content in the target format")


class ReportResponse(BaseModel):
    """Response containing the generated recommendation report."""

    report_id: str = Field(default="", description="Unique report identifier")
    request_id: str = Field(default="", description="The original request ID this report is for")
    generated_at: str = Field(default="", description="ISO-8601 timestamp of generation")
    format: str = Field(default="markdown", description="Report format")
    title: str = Field(default="", description="Report title")
    summary: str = Field(default="", description="Executive summary")
    generation_source: str = Field(default="rule", description="Report text generation source: rule / llm / fallback")
    llm_trace_id: str = Field(default="", description="LLM trace id when LLM was used")
    llm_fallback_reason: str = Field(default="", description="Non-sensitive LLM fallback reason")
    sections: list[ReportSection] = Field(default_factory=list, description="Report sections")
    raw_content: str = Field(default="", description="Full report content as a single string")
