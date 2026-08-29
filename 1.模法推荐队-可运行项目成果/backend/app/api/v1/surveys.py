"""Standardized human explanation-comprehension survey endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response

from app.core.security import get_current_user
from app.schemas.auth import UserContext
from app.schemas.survey import (
    SurveyCampaignCreateRequest,
    SurveyCampaignCreateResponse,
    SurveyDefinitionResponse,
    SurveySubmissionRequest,
    SurveySubmissionResponse,
    SurveySummaryResponse,
)
from app.services.audit_service import get_audit_service
from app.services.survey_service import QUESTIONS, SurveyError, get_survey_service


router = APIRouter()


def _require_explicit_auditor(x_user_id: str | None, user: UserContext) -> None:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="管理操作必须显式提供 X-User-Id")
    if not user.can_view_audit:
        raise HTTPException(status_code=403, detail="当前用户无问卷管理权限")


@router.post("/surveys/campaigns", response_model=SurveyCampaignCreateResponse)
async def create_survey_campaign(
    request: SurveyCampaignCreateRequest,
    x_user_id: str | None = Header(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    _require_explicit_auditor(x_user_id, current_user)
    try:
        campaign, tokens = get_survey_service().create_campaign(request)
    except SurveyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_audit_service().record(
        "survey_campaign_created",
        current_user,
        request_id=campaign.campaign_id,
        payload_summary={
            "invite_count": campaign.invitation_count,
            "minimum_respondents": campaign.minimum_respondents,
            "samples_per_respondent": campaign.samples_per_respondent,
        },
    )
    return SurveyCampaignCreateResponse(campaign=campaign, invitation_tokens=tokens)


@router.get("/surveys/campaigns/{campaign_id}", response_model=SurveyDefinitionResponse)
async def get_survey_definition(campaign_id: str):
    try:
        campaign = get_survey_service().campaign_info(campaign_id)
    except SurveyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SurveyDefinitionResponse(campaign=campaign, questions=QUESTIONS)


@router.post("/surveys/responses", response_model=SurveySubmissionResponse)
async def submit_survey_response(request: SurveySubmissionRequest):
    try:
        return get_survey_service().submit(request)
    except SurveyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/surveys/campaigns/{campaign_id}/summary", response_model=SurveySummaryResponse)
async def get_survey_summary(
    campaign_id: str,
    x_user_id: str | None = Header(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    _require_explicit_auditor(x_user_id, current_user)
    try:
        summary = get_survey_service().summary(campaign_id)
    except SurveyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_audit_service().record(
        "survey_summary_viewed",
        current_user,
        request_id=campaign_id,
        payload_summary={
            "complete_respondents": summary.complete_respondents,
            "metric_threshold_met": summary.metric_threshold_met,
            "formal_evidence_verified": summary.formal_evidence_verified,
        },
    )
    return summary


@router.get("/surveys/campaigns/{campaign_id}/export.csv")
async def export_survey_responses(
    campaign_id: str,
    x_user_id: str | None = Header(default=None),
    current_user: UserContext = Depends(get_current_user),
):
    _require_explicit_auditor(x_user_id, current_user)
    try:
        content = get_survey_service().export_csv(campaign_id)
    except SurveyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_audit_service().record(
        "survey_responses_exported",
        current_user,
        request_id=campaign_id,
        payload_summary={"format": "csv"},
    )
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{campaign_id}_responses.csv"'},
    )
