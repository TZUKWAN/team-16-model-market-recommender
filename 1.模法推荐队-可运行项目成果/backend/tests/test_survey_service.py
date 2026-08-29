"""Service tests for real-person survey collection without fake evidence claims."""

from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from app.repositories.runtime_repository import SQLiteRuntimeRepository
from app.schemas.survey import (
    SurveyAnswers,
    SurveyCampaignCreateRequest,
    SurveyOpenFeedback,
    SurveySubmissionRequest,
)
from app.services.survey_service import SurveyError, SurveyService


def campaign_request(**overrides):
    payload = {
        "name": "解释理解度验收",
        "invite_count": 2,
        "samples_per_respondent": 2,
        "minimum_respondents": 1,
        "required_roles": ["business"],
        "required_scenarios": ["credit_risk", "customer_marketing", "operation_management"],
    }
    payload.update(overrides)
    return SurveyCampaignCreateRequest(**payload)


def submission(campaign_id, token, sample_id, *, role="business", scenario="credit_risk", score=5, feedback=None):
    return SurveySubmissionRequest(
        campaign_id=campaign_id,
        invitation_token=token,
        sample_id=sample_id,
        scenario_id=scenario,
        department=role,
        role=role,
        answers=SurveyAnswers(**{f"q{i}": score for i in range(1, 9)}),
        open_feedback=SurveyOpenFeedback(**(feedback or {})),
        consent_confirmed=True,
    )


def test_campaign_stores_only_token_hashes(tmp_path):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    campaign, tokens = service.create_campaign(campaign_request())

    persisted = (tmp_path / "campaigns" / f"{campaign.campaign_id}.json").read_text(encoding="utf-8")
    assert len(tokens) == 2
    assert all(token not in persisted for token in tokens)
    assert "invitation_hashes" in persisted


def test_submission_is_unique_per_sample_and_token_has_fixed_capacity(tmp_path):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    campaign, tokens = service.create_campaign(campaign_request())

    first = service.submit(submission(campaign.campaign_id, tokens[0], "sample-1"))
    second = service.submit(submission(campaign.campaign_id, tokens[0], "sample-2", scenario="customer_marketing"))

    assert first.respondent_complete is False
    assert second.respondent_complete is True
    with pytest.raises(SurveyError, match="重复评价"):
        service.submit(submission(campaign.campaign_id, tokens[0], "sample-1"))
    with pytest.raises(SurveyError, match="规定样例数"):
        service.submit(submission(campaign.campaign_id, tokens[0], "sample-3"))


@pytest.mark.parametrize(
    "text",
    [
        "请联系13812345678",
        "身份证320101199001011234",
        "银行卡6222021234567890123",
        "api_key=" + "sk-" + "secret-value-" + "123456789",
    ],
)
def test_sensitive_open_feedback_is_rejected(tmp_path, text):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    campaign, tokens = service.create_campaign(campaign_request())

    with pytest.raises(SurveyError, match="敏感信息"):
        service.submit(
            submission(
                campaign.campaign_id,
                tokens[0],
                "sample-1",
                feedback={"still_unclear": text},
            )
        )


def test_completed_human_threshold_is_separate_from_external_identity_verification(tmp_path):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    roles = ["business", "risk", "product", "operations", "compliance", "technology"]
    scenarios = ["credit_risk", "customer_marketing", "operation_management"]
    campaign, tokens = service.create_campaign(
        campaign_request(
            invite_count=30,
            minimum_respondents=30,
            required_roles=roles,
        )
    )
    for index, token in enumerate(tokens):
        role = roles[index % len(roles)]
        service.submit(
            submission(
                campaign.campaign_id,
                token,
                f"sample-{index}-a",
                role=role,
                scenario=scenarios[index % len(scenarios)],
            )
        )
        service.submit(
            submission(
                campaign.campaign_id,
                token,
                f"sample-{index}-b",
                role=role,
                scenario=scenarios[(index + 1) % len(scenarios)],
            )
        )

    summary = service.summary(campaign.campaign_id)

    assert summary.complete_respondents == 30
    assert summary.scored_responses == 60
    assert summary.comprehensibility_pct == 100.0
    assert summary.metric_threshold_met is True
    assert summary.formal_evidence_verified is False
    assert summary.evidence_status == "eligible_for_external_identity_verification"
    assert summary.missing_required_roles == []
    assert summary.missing_required_scenarios == []
    csv_text = service.export_csv(campaign.campaign_id)
    assert csv_text.startswith("\ufeff")
    assert all(token not in csv_text for token in tokens)


def test_partial_respondents_are_not_scored_as_formal_metric(tmp_path):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    campaign, tokens = service.create_campaign(campaign_request())
    service.submit(submission(campaign.campaign_id, tokens[0], "sample-1", score=5))

    summary = service.summary(campaign.campaign_id)

    assert summary.total_submissions == 1
    assert summary.complete_respondents == 0
    assert summary.scored_responses == 0
    assert summary.comprehensibility_pct == 0.0
    assert summary.metric_threshold_met is False


def test_csv_export_cells_neutralize_spreadsheet_formulas():
    assert SurveyService._csv_safe_cell("=HYPERLINK(\"https://example.test\")") == "'=HYPERLINK(\"https://example.test\")"
    assert SurveyService._csv_safe_cell("+cmd") == "'+cmd"
    assert SurveyService._csv_safe_cell("ordinary text") == "ordinary text"


def test_response_log_never_contains_raw_invitation_token(tmp_path):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    campaign, tokens = service.create_campaign(campaign_request())
    service.submit(submission(campaign.campaign_id, tokens[0], "sample-1"))

    raw = (tmp_path / "responses.jsonl").read_text(encoding="utf-8")
    row = json.loads(raw)
    assert tokens[0] not in raw
    assert row["source_type"] == "human_submitted_identity_unverified"


def test_acceptance_campaign_can_never_become_human_metric_evidence(tmp_path):
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    campaign, tokens = service.create_campaign(
        campaign_request(evidence_mode="acceptance_test")
    )
    service.submit(submission(campaign.campaign_id, tokens[0], "sample-1", score=5))
    service.submit(submission(campaign.campaign_id, tokens[0], "sample-2", score=5))

    summary = service.summary(campaign.campaign_id)
    raw = (tmp_path / "responses.jsonl").read_text(encoding="utf-8")

    assert summary.comprehensibility_pct == 100.0
    assert summary.metric_threshold_met is False
    assert summary.evidence_status == "acceptance_test_non_evidence"
    assert summary.source_type == "automated_acceptance_test_non_evidence"
    assert "automated_acceptance_test_non_evidence" in raw


def test_sqlite_survey_survives_restart_and_enforces_capacity_across_workers(tmp_path):
    db_path = tmp_path / "runtime.db"
    service = SurveyService(repository=SQLiteRuntimeRepository(db_path))
    campaign, tokens = service.create_campaign(campaign_request())

    def submit_from_worker(index: int):
        worker = SurveyService(repository=SQLiteRuntimeRepository(db_path))
        try:
            return worker.submit(
                submission(campaign.campaign_id, tokens[0], f"sample-{index}")
            )
        except SurveyError:
            return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(submit_from_worker, range(30)))

    accepted = [result for result in results if result is not None]
    assert len(accepted) == 2
    reopened = SurveyService(repository=SQLiteRuntimeRepository(db_path))
    summary = reopened.summary(campaign.campaign_id)
    assert summary.total_submissions == 2
    assert summary.complete_respondents == 1

    database_bytes = b"".join(
        path.read_bytes()
        for path in tmp_path.glob("runtime.db*")
        if path.is_file()
    )
    assert tokens[0].encode("ascii") not in database_bytes
    persisted_campaign = reopened.get_campaign(campaign.campaign_id)
    assert persisted_campaign["invitation_hashes"] == [
        reopened._token_hash(token) for token in tokens
    ]
