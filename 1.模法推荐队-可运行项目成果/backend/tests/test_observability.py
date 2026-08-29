import json
import logging

from app.core.logging import JsonLogFormatter, SensitiveDataFilter


def test_request_id_is_shared_by_response_header_and_error_body(client):
    request_id = "request-observe-001"
    correlation_id = "workflow-observe-001"
    response = client.post(
        "/api/v1/parse-demand",
        headers={"X-Request-ID": request_id, "X-Correlation-ID": correlation_id},
        json={},
    )
    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == request_id
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert response.json()["request_id"] == request_id


def test_invalid_incoming_request_id_is_replaced(client):
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "Bearer secret-value"},
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "Bearer secret-value"
    assert len(response.headers["X-Request-ID"]) >= 8


def test_structured_log_filter_redacts_credentials_and_personal_identifiers():
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1,
        "Authorization=Bearer abc.def.ghi api_key=secretvalue123456 phone=13812345678 id=320101199001011234 card=6222021234567890123",
        (), None,
    )
    assert SensitiveDataFilter().filter(record)
    payload = json.loads(JsonLogFormatter().format(record))
    message = payload["message"]
    assert message.count("[REDACTED]") >= 5
    assert "abc.def.ghi" not in message
    assert "13812345678" not in message
    assert "6222021234567890123" not in message


def test_health_exposes_aggregate_error_counts_without_request_content(client):
    client.get("/api/v1/does-not-exist")
    health = client.get("/api/v1/health").json()
    assert health["request_metrics"]["total_requests"] >= 1
    assert "status_counts" in health["request_metrics"]
