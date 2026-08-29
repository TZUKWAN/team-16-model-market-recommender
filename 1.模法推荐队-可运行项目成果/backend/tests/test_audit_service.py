"""Tests for audit JSONL service and API."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.audit_service import AuditService, get_audit_service
from app.services.auth_service import get_auth_service
from app.repositories.runtime_repository import SQLiteRuntimeRepository


client = TestClient(app)


def test_audit_service_uses_sqlite_when_repository_is_supplied(tmp_path: Path):
    path = tmp_path / "runtime.db"
    service = AuditService(repository=SQLiteRuntimeRepository(path))
    user = get_auth_service().get_user("risk_user")
    created = service.record("model_invoke", user, model_id="RISK_001")

    reopened = AuditService(repository=SQLiteRuntimeRepository(path))
    events = reopened.query(event_type="model_invoke", user_id="risk_user")
    assert [event.event_id for event in events] == [created.event_id]


def test_audit_service_writes_and_queries_jsonl(tmp_path: Path):
    service = AuditService(log_path=tmp_path / "audit_events.jsonl")
    user = get_auth_service().get_user("risk_user")

    event = service.record(
        "model_invoke",
        user,
        model_id="RISK_001",
        task_id="task-1",
        result_type="risk",
        payload_summary={"raw_text": "x" * 300, "input_keys": ["a", "b"]},
    )
    events = service.query(event_type="model_invoke", user_id="risk_user")

    assert event.event_id
    assert len(events) == 1
    assert events[0].model_id == "RISK_001"
    assert len(events[0].payload_summary["raw_text"]) == 160


def test_audit_api_records_parse_event_and_requires_audit_permission(tmp_path: Path, monkeypatch):
    service = get_audit_service()
    temp_log = tmp_path / "audit_events.jsonl"
    temp_log.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(service, "log_path", temp_log)

    parse_resp = client.post(
        "/api/v1/parse-demand",
        json={"raw_text": "帮我筛选县域新客做首贷营销。"},
        headers={"X-User-Id": "business_user"},
    )
    denied_resp = client.get(
        "/api/v1/audit/events",
        headers={"X-User-Id": "business_user"},
    )
    audit_resp = client.get(
        "/api/v1/audit/events?event_type=parse_demand&user_id=business_user",
        headers={"X-User-Id": "auditor"},
    )

    assert parse_resp.status_code == 200
    assert denied_resp.status_code == 403
    assert audit_resp.status_code == 200
    data = audit_resp.json()
    assert data["total"] == 1
    assert data["events"][0]["event_type"] == "parse_demand"
    assert data["events"][0]["user_id"] == "business_user"
