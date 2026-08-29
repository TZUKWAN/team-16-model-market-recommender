"""Schemas for anonymous human explanation-comprehension surveys."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SurveyRole = Literal[
    "business",
    "risk",
    "product",
    "operations",
    "compliance",
    "technology",
]
SurveyScenario = Literal["credit_risk", "customer_marketing", "operation_management"]


class SurveyAnswers(BaseModel):
    q1: int = Field(ge=1, le=5)
    q2: int = Field(ge=1, le=5)
    q3: int = Field(ge=1, le=5)
    q4: int = Field(ge=1, le=5)
    q5: int = Field(ge=1, le=5)
    q6: int = Field(ge=1, le=5)
    q7: int = Field(ge=1, le=5)
    q8: int = Field(ge=1, le=5)


class SurveyOpenFeedback(BaseModel):
    most_helpful: str = Field(default="", max_length=1000)
    still_unclear: str = Field(default="", max_length=1000)
    main_risk: str = Field(default="", max_length=1000)
    desired_improvements: str = Field(default="", max_length=1000)


class SurveyCampaignCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    invite_count: int = Field(default=30, ge=1, le=500)
    samples_per_respondent: int = Field(default=2, ge=2, le=10)
    minimum_respondents: int = Field(default=30, ge=1, le=500)
    evidence_mode: Literal["human_survey", "acceptance_test"] = "human_survey"
    required_roles: list[SurveyRole] = Field(
        default_factory=lambda: [
            "business", "risk", "product", "operations", "compliance", "technology"
        ]
    )
    required_scenarios: list[SurveyScenario] = Field(
        default_factory=lambda: ["credit_risk", "customer_marketing", "operation_management"]
    )


class SurveyCampaignInfo(BaseModel):
    campaign_id: str
    name: str
    status: Literal["active", "closed"] = "active"
    created_at: str
    samples_per_respondent: int
    minimum_respondents: int
    required_roles: list[SurveyRole]
    required_scenarios: list[SurveyScenario]
    invitation_count: int
    evidence_mode: Literal["human_survey", "acceptance_test"] = "human_survey"
    questionnaire_version: str = "explanation-v1"


class SurveyCampaignCreateResponse(BaseModel):
    campaign: SurveyCampaignInfo
    invitation_tokens: list[str]
    token_notice: str = "邀请码仅返回一次；服务端只保存哈希。"


class SurveyQuestionDefinition(BaseModel):
    question_id: str
    text: str
    dimension: str


class SurveyDefinitionResponse(BaseModel):
    campaign: SurveyCampaignInfo
    questions: list[SurveyQuestionDefinition]
    scale_min: int = 1
    scale_max: int = 5
    understandable_threshold: int = 4


class SurveySubmissionRequest(BaseModel):
    campaign_id: str = Field(pattern=r"^SURV_[A-F0-9]{12}$")
    invitation_token: str = Field(min_length=20, max_length=200)
    sample_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{3,120}$")
    scenario_id: SurveyScenario
    department: SurveyRole
    role: SurveyRole
    answers: SurveyAnswers
    open_feedback: SurveyOpenFeedback = Field(default_factory=SurveyOpenFeedback)
    consent_confirmed: bool


class SurveySubmissionResponse(BaseModel):
    response_id: str
    accepted_samples: int
    required_samples: int
    respondent_complete: bool
    formal_evidence_verified: bool = False


class SurveyMetricBucket(BaseModel):
    count: int = 0
    average_score: float = 0.0
    understandable_rate_pct: float = 0.0


class SurveySummaryResponse(BaseModel):
    campaign_id: str
    questionnaire_version: str = "explanation-v1"
    total_submissions: int = 0
    unique_invited_respondents: int = 0
    complete_respondents: int = 0
    scored_responses: int = 0
    core_answer_count: int = 0
    understandable_count: int = 0
    comprehensibility_pct: float = 0.0
    per_question: dict[str, SurveyMetricBucket] = Field(default_factory=dict)
    per_role: dict[str, SurveyMetricBucket] = Field(default_factory=dict)
    per_scenario: dict[str, SurveyMetricBucket] = Field(default_factory=dict)
    missing_required_roles: list[str] = Field(default_factory=list)
    missing_required_scenarios: list[str] = Field(default_factory=list)
    low_dimensions: list[str] = Field(default_factory=list)
    metric_threshold_met: bool = False
    formal_evidence_verified: bool = False
    evidence_status: Literal[
        "collecting",
        "metric_below_target",
        "eligible_for_external_identity_verification",
        "acceptance_test_non_evidence",
    ] = "collecting"
    source_type: str = "human_submitted_identity_unverified"
