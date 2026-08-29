"""API tests for survey campaign authorization and token-based submission."""


def create_payload():
    return {
        "name": "解释理解度验收",
        "invite_count": 1,
        "samples_per_respondent": 2,
        "minimum_respondents": 1,
        "required_roles": ["business"],
        "required_scenarios": ["credit_risk", "customer_marketing", "operation_management"],
        "evidence_mode": "human_survey",
    }


def response_payload(campaign_id, token, sample_id="sample-1"):
    return {
        "campaign_id": campaign_id,
        "invitation_token": token,
        "sample_id": sample_id,
        "scenario_id": "credit_risk",
        "department": "business",
        "role": "business",
        "answers": {f"q{i}": 5 for i in range(1, 9)},
        "open_feedback": {},
        "consent_confirmed": True,
    }


def test_campaign_management_requires_explicit_authorized_identity(client):
    missing = client.post("/api/v1/surveys/campaigns", json=create_payload())
    forbidden = client.post(
        "/api/v1/surveys/campaigns",
        json=create_payload(),
        headers={"X-User-Id": "risk_user"},
    )

    assert missing.status_code == 401
    assert forbidden.status_code == 403


def test_public_definition_token_submission_summary_and_csv_export(client):
    created = client.post(
        "/api/v1/surveys/campaigns",
        json=create_payload(),
        headers={"X-User-Id": "admin"},
    )
    assert created.status_code == 200
    body = created.json()
    campaign_id = body["campaign"]["campaign_id"]
    token = body["invitation_tokens"][0]

    definition = client.get(f"/api/v1/surveys/campaigns/{campaign_id}")
    assert definition.status_code == 200
    assert len(definition.json()["questions"]) == 8
    assert "invitation_tokens" not in definition.text

    submitted = client.post(
        "/api/v1/surveys/responses",
        json=response_payload(campaign_id, token),
    )
    assert submitted.status_code == 200
    assert submitted.json()["formal_evidence_verified"] is False

    unauthorized_summary = client.get(f"/api/v1/surveys/campaigns/{campaign_id}/summary")
    summary = client.get(
        f"/api/v1/surveys/campaigns/{campaign_id}/summary",
        headers={"X-User-Id": "auditor"},
    )
    exported = client.get(
        f"/api/v1/surveys/campaigns/{campaign_id}/export.csv",
        headers={"X-User-Id": "admin"},
    )

    assert unauthorized_summary.status_code == 401
    assert summary.status_code == 200
    assert summary.json()["total_submissions"] == 1
    assert summary.json()["formal_evidence_verified"] is False
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert token not in exported.text


def test_invalid_invitation_token_is_rejected_without_leaking_token(client):
    created = client.post(
        "/api/v1/surveys/campaigns",
        json=create_payload(),
        headers={"X-User-Id": "admin"},
    ).json()
    campaign_id = created["campaign"]["campaign_id"]
    invalid_token = "this-is-an-invalid-invitation-token"

    response = client.post(
        "/api/v1/surveys/responses",
        json=response_payload(campaign_id, invalid_token),
    )

    assert response.status_code == 422
    assert invalid_token not in response.text
