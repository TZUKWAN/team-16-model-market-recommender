from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_rejects_request_larger_than_configured_limit():
    response = client.post(
        "/api/v1/parse-demand",
        content=b"x" * (2 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert "size limit" in response.json()["detail"]


def test_rejects_excessively_nested_json():
    value = "leaf"
    for _ in range(25):
        value = {"nested": value}
    response = client.post("/api/v1/parse-demand", json={"raw_text": "test", "context": value})
    assert response.status_code == 400
    assert "depth limit" in response.json()["detail"]


def test_normal_json_request_still_reaches_endpoint():
    response = client.post("/api/v1/parse-demand", json={"raw_text": "农户贷款贷前风险评估"})
    assert response.status_code == 200


def test_bodyless_get_request_is_not_consumed_or_blocked():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["app"] == "model-market-assistant"
