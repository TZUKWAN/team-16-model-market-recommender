"""Migration, export, integrity and rollback tests for runtime SQLite storage."""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

from app.repositories.runtime_repository import SQLiteRuntimeRepository


ROOT = Path(__file__).resolve().parents[2]


def _module():
    spec = spec_from_file_location("migrate_runtime_storage", ROOT / "scripts" / "migrate_runtime_storage.py")
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_legacy(data_dir: Path) -> None:
    files = {
        "conversations/c1.json": {"session_id": "c1", "created_at": "1", "turns": []},
        "surveys/campaigns/s1.json": {
            "campaign_id": "s1", "created_at": "2", "invitation_hashes": ["hash-only"]
        },
    }
    for relative, payload in files.items():
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    jsonl = {
        "audit/audit_events.jsonl": {"event_id": "a1", "timestamp": "3"},
        "feedback/feedback_events.jsonl": {
            "event_id": "f1", "timestamp": "4", "request_id": "q1", "action": "adopt"
        },
        "surveys/responses.jsonl": {
            "response_id": "r1", "submitted_at": "5", "campaign_id": "s1",
            "respondent_key": "respondent-hash", "sample_id": "sample-1",
        },
        "recommendation_versions/c1.jsonl": {
            "version_id": "v1", "session_id": "c1", "request_id": "q1", "created_at": "6",
            "version_number": 1,
        },
    }
    for relative, payload in jsonl.items():
        path = data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_migration_is_idempotent_exports_and_restores(tmp_path):
    module = _module()
    data_dir = tmp_path / "legacy"
    db_path = tmp_path / "runtime.db"
    backup_path = tmp_path / "before-second-run.db"
    _write_legacy(data_dir)

    first = module.migrate(data_dir, db_path)
    second = module.migrate(data_dir, db_path, backup_path)
    assert first["status"] == "ok"
    assert sum(first["imported"].values()) == 6
    assert second["status"] == "ok"
    assert sum(second["already_present"].values()) == 6

    exported = module.export_legacy(db_path, tmp_path / "export")
    assert exported["status"] == "ok"
    assert (tmp_path / "export" / "conversations" / "c1.json").is_file()
    assert (tmp_path / "export" / "recommendation_versions" / "c1.jsonl").is_file()

    repository = SQLiteRuntimeRepository(db_path)
    repository.insert("extra", "x", {"created_at": "7"})
    assert repository.count("extra") == 1
    repository.restore_from(backup_path)
    assert repository.count("extra") == 0
    assert repository.integrity_check() == (True, "ok")


def test_migration_reports_corrupt_jsonl_with_line_number(tmp_path):
    module = _module()
    data_dir = tmp_path / "legacy"
    path = data_dir / "audit" / "audit_events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"event_id":"ok"}\nnot-json\n', encoding="utf-8")

    result = module.migrate(data_dir, tmp_path / "runtime.db")
    assert result["status"] == "failed"
    assert result["imported"] == {"audit_events": 1}
    assert any("audit_events.jsonl:2" in error for error in result["errors"])
