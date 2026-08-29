"""Scenario library endpoints — list, match, and generate scripts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.schemas.auth import UserContext
from app.schemas.scenario import (
    BusinessScenario,
    ScenarioMatchRequest,
    ScenarioMatchResponse,
    ScriptGenerateRequest,
    ScriptGenerateResponse,
)
from app.services.scenario_service import get_scenario_service
from app.services.script_generator import get_script_generator

router = APIRouter()


@router.get("/scenarios", response_model=list[BusinessScenario])
async def list_scenarios(
    domain: str = Query("", description="按业务领域过滤: credit_risk/customer_marketing/operation_management"),
    current_user: UserContext = Depends(get_current_user),
):
    """List business scenarios in the library, optionally filtered by domain."""
    return get_scenario_service().list_scenarios(domain)


@router.post("/scenarios/match", response_model=ScenarioMatchResponse)
async def match_scenarios(
    request: ScenarioMatchRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Match a parsed demand to the top-k most relevant business scenarios."""
    return get_scenario_service().match(request.parse_result, request.top_k)


@router.post("/scenarios/{scenario_id}/generate-script", response_model=ScriptGenerateResponse)
async def generate_script(
    scenario_id: str,
    request: ScriptGenerateRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Generate a scenario-specific script via LLM (with rule-based fallback)."""
    if request.scenario_id and request.scenario_id != scenario_id:
        raise HTTPException(status_code=400, detail="路径 scenario_id 与请求体不一致")
    service = get_scenario_service()
    if service.get_scenario(scenario_id) is None:
        raise HTTPException(status_code=404, detail=f"场景 {scenario_id} 不存在")
    return get_script_generator().generate(
        scenario_id,
        request.parse_result,
        request.script_type,
    )
