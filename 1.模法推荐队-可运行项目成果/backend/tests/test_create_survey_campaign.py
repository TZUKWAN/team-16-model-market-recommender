"""Tests for private survey invitation artifact creation."""

import csv
import importlib.util
from pathlib import Path

from app.schemas.survey import SurveyCampaignCreateRequest
from app.services.survey_service import SurveyService


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "create_survey_campaign.py"
    spec = importlib.util.spec_from_file_location("create_survey_campaign", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_campaign_artifacts_keep_plaintext_tokens_only_in_private_csv(tmp_path):
    module = load_script()
    service = SurveyService(tmp_path / "campaigns", tmp_path / "responses.jsonl")
    request = SurveyCampaignCreateRequest(
        name="真人问卷验收",
        invite_count=2,
        minimum_respondents=1,
        samples_per_respondent=2,
        required_roles=["business"],
        required_scenarios=["credit_risk", "customer_marketing", "operation_management"],
    )

    campaign_id, invitation_path = module.create_campaign_artifacts(
        service,
        request,
        tmp_path / "invitations",
    )

    with invitation_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    campaign_text = (tmp_path / "campaigns" / f"{campaign_id}.json").read_text(encoding="utf-8")
    assert len(rows) == 2
    assert all(row["invitation_token"] for row in rows)
    assert all(row["invitation_token"] not in campaign_text for row in rows)
    assert invitation_path.name.endswith(".private.csv")
