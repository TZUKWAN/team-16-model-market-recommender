"""API tests for model invocation endpoints."""

from fastapi.testclient import TestClient

from app.integrations.http_model_market_client import HttpModelMarketClient
from app.integrations import model_market_client as market_module
from app.main import app

client = TestClient(app)


def teardown_function():
    market_module.reset_model_market_client_for_tests()


def test_demo_invoke_task_status_result_and_schema_flow():
    invoke_resp = client.post(
        "/api/v1/models/MKT_001/invoke",
        json={
            "input_data": {"customer_profile": {"age": 35}, "transaction_flow": [1, 2, 3]},
            "async_mode": True,
            "request_context": {"operator": "demo_user"},
        },
    )

    assert invoke_resp.status_code == 200
    invoke_data = invoke_resp.json()
    assert invoke_data["model_id"] == "MKT_001"
    assert invoke_data["demo_data"] is True
    assert invoke_data["task_id"].startswith("demo-task-")
    assert invoke_data["result"]["demo_data"] is True
    assert invoke_data["result"]["result_type"] == "marketing"
    assert invoke_data["result"]["desensitized_notice"]
    assert {"customer_id_masked", "product", "conversion_probability", "priority", "touch_channel"}.issubset(
        invoke_data["result"]["rows"][0]
    )

    task_id = invoke_data["task_id"]
    status_resp = client.get(f"/api/v1/tasks/{task_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "completed"
    assert status_resp.json()["demo_data"] is True

    result_resp = client.get(f"/api/v1/tasks/{task_id}/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert result_data["demo_data"] is True
    assert result_data["result"]["desensitized_notice"]
    assert result_data["result"]["result_type"] == "marketing"

    schema_resp = client.get("/api/v1/models/MKT_001/result-schema")
    assert schema_resp.status_code == 200
    schema_data = schema_resp.json()
    assert schema_data["model_id"] == "MKT_001"
    assert schema_data["demo_data"] is True
    assert schema_data["result_schema"]["type"] == "object"
    assert "conversion_probability" in schema_data["result_schema"]["properties"]["rows"]["items"]["properties"]


def test_real_unconfigured_invoke_returns_clear_503():
    market_module._model_market_client = HttpModelMarketClient(base_url="", api_key="")

    resp = client.post(
        "/api/v1/models/MKT_001/invoke",
        json={"input_data": {"customer_profile": {"age": 35}}},
    )

    assert resp.status_code == 503
    assert resp.json()["code"] == "HTTP_503"
    assert "未配置" in resp.json()["message"]
