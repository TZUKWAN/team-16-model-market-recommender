"""Schemas for business scenario library and LLM script generation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TypicalScripts(BaseModel):
    """Pre-authored typical scripts bundled with a scenario."""

    marketing: str = ""
    risk_notice: str = ""
    outreach: str = ""


class BusinessScenario(BaseModel):
    """A business scenario entry in the scenario library."""

    scenario_id: str = ""
    name: str = ""
    domain: str = ""
    business_stage: str = ""
    description: str = ""
    typical_scripts: TypicalScripts = Field(default_factory=TypicalScripts)
    applicable_models: list[str] = Field(default_factory=list)
    data_requirements: list[str] = Field(default_factory=list)
    compliance_notes: str = ""
    keywords: list[str] = Field(default_factory=list)


class ScenarioMatchRequest(BaseModel):
    """Request to match a parsed demand to business scenarios."""

    parse_result: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=3, ge=1, le=10)


class ScenarioMatchItem(BaseModel):
    """One matched scenario with score and evidence."""

    scenario: BusinessScenario
    match_score: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    match_reason: str = ""


class ScenarioMatchResponse(BaseModel):
    """Ranked scenario matches for a demand."""

    matches: list[ScenarioMatchItem] = Field(default_factory=list)
    total_scenarios: int = 0


class ScriptGenerateRequest(BaseModel):
    """Request to generate a scenario-specific script via LLM."""

    scenario_id: str = ""
    parse_result: dict[str, Any] = Field(default_factory=dict)
    script_type: str = Field(default="comprehensive")  # marketing/risk_notice/outreach/comprehensive


class GeneratedScript(BaseModel):
    """A generated script with provenance and disclaimer."""

    scenario_id: str = ""
    scenario_name: str = ""
    script_type: str = ""
    content: str = ""
    disclaimer: str = "本话术由AI生成，需人工复核后方可用于业务场景。"
    llm_used: bool = False
    basis: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_trace_id: str = ""
    status: str = "ok"  # ok, repaired, fallback
    repair_attempted: bool = False
    fallback_reason: str = ""
    validation: dict[str, Any] = Field(default_factory=dict)


class ScriptGenerateResponse(BaseModel):
    """Response wrapping a generated script."""

    script: GeneratedScript
