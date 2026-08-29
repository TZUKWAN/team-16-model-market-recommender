"""Tests for local role and institution access control."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth_service import get_auth_service


client = TestClient(app)


def test_default_user_is_admin_for_demo_compatibility():
    user = get_auth_service().get_user(None)

    assert user.user_id == "admin"
    assert set(user.permitted_domains) == {
        "credit_risk",
        "customer_marketing",
        "operation_management",
    }


def test_unknown_user_has_no_model_access():
    user = get_auth_service().get_user("missing_user")
    decision = get_auth_service().can_access_model(user, "RISK_001", "invoke")

    assert decision.allowed is False
    assert user.role == "unknown"


def test_risk_user_can_recommend_risk_models():
    parse_resp = client.post("/api/v1/parse-demand", json={
        "raw_text": "帮我做农户小额贷款的贷前准入风控，识别欺诈风险。",
    })
    rec_resp = client.post(
        "/api/v1/recommend-models",
        json={"parse_result": parse_resp.json(), "top_k": 5},
        headers={"X-User-Id": "risk_user"},
    )

    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert data["recommendations"]
    assert all(item["model_id"].startswith(("RISK_", "OFFICIAL_")) for item in data["recommendations"])


def test_business_user_cannot_invoke_risk_model():
    response = client.post(
        "/api/v1/models/RISK_001/invoke",
        json={"input_data": {}, "async_mode": False},
        headers={"X-User-Id": "business_user"},
    )

    assert response.status_code == 403


def test_auditor_cannot_invoke_model_but_can_view_unknown_task_context():
    invoke_resp = client.post(
        "/api/v1/models/MKT_001/invoke",
        json={"input_data": {}, "async_mode": False},
        headers={"X-User-Id": "auditor"},
    )
    status_resp = client.get(
        "/api/v1/tasks/demo-task-not-registered",
        headers={"X-User-Id": "auditor"},
    )

    assert invoke_resp.status_code == 403
    assert status_resp.status_code == 200


def test_task_result_is_limited_to_allowed_domain_or_owner():
    invoke_resp = client.post(
        "/api/v1/models/MKT_001/invoke",
        json={"input_data": {}, "async_mode": False},
        headers={"X-User-Id": "business_user"},
    )
    assert invoke_resp.status_code == 200
    task_id = invoke_resp.json()["task_id"]

    owner_resp = client.get(
        f"/api/v1/tasks/{task_id}/result",
        headers={"X-User-Id": "business_user"},
    )
    risk_resp = client.get(
        f"/api/v1/tasks/{task_id}/result",
        headers={"X-User-Id": "risk_user"},
    )

    assert owner_resp.status_code == 200
    assert risk_resp.status_code == 403
