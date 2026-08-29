"""Migrate legacy runtime JSON/JSONL data to SQLite and export it back safely."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.repositories.runtime_repository import SQLiteRuntimeRepository  # noqa: E402


def _json_file(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: {exc}")
        return []
    if not isinstance(value, dict):
        errors.append(f"{path}: expected JSON object")
        return []
    return [value]


def _jsonl_file(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        errors.append(f"{path}: {exc}")
        return rows
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_number}: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path}:{line_number}: expected JSON object")
            continue
        rows.append(value)
    return rows


def _sources(data_dir: Path, errors: list[str]) -> Iterable[tuple[str, dict[str, Any]]]:
    for path in sorted((data_dir / "conversations").glob("*.json")):
        for row in _json_file(path, errors):
            yield "conversation_sessions", row
    for path, namespace in (
        (data_dir / "audit" / "audit_events.jsonl", "audit_events"),
        (data_dir / "feedback" / "feedback_events.jsonl", "feedback_events"),
        (data_dir / "surveys" / "responses.jsonl", "survey_responses"),
    ):
        if path.exists():
            for row in _jsonl_file(path, errors):
                yield namespace, row
    for path in sorted((data_dir / "surveys" / "campaigns").glob("*.json")):
        for row in _json_file(path, errors):
            yield "survey_campaigns", row
    for path in sorted((data_dir / "recommendation_versions").glob("*.jsonl")):
        for row in _jsonl_file(path, errors):
            yield "recommendation_versions", row


def _identity(namespace: str, row: dict[str, Any]) -> tuple[str, str, str | None]:
    if namespace == "conversation_sessions":
        record_id = str(row.get("session_id") or "")
        return record_id, record_id, f"legacy:{namespace}:{record_id}"
    if namespace == "audit_events":
        record_id = str(row.get("event_id") or "")
        partition = str(row.get("legal_entity_id") or row.get("institution_id") or "")
        return record_id, partition, f"legacy:{namespace}:{record_id}"
    if namespace == "feedback_events":
        record_id = str(row.get("event_id") or "")
        if row.get("action") == "recommended":
            key = f"{row.get('evidence_mode', 'human')}:{row.get('request_id', '')}:{row.get('model_id', '')}:recommended"
        else:
            key = f"legacy:{namespace}:{record_id}"
        return record_id, str(row.get("request_id") or ""), key
    if namespace == "survey_campaigns":
        record_id = str(row.get("campaign_id") or "")
        return record_id, record_id, f"legacy:{namespace}:{record_id}"
    if namespace == "survey_responses":
        record_id = str(row.get("response_id") or "")
        partition = f"{row.get('campaign_id', '')}:{row.get('respondent_key', '')}"
        key = f"{partition}:{row.get('sample_id', '')}"
        return record_id, partition, key
    record_id = str(row.get("version_id") or "")
    session_id = str(row.get("session_id") or "")
    stable_key = str(row.get("idempotency_key") or row.get("request_id") or record_id)
    return record_id, session_id, f"{session_id}:{stable_key}"


def migrate(data_dir: Path, db_path: Path, backup_path: Path | None = None) -> dict[str, Any]:
    repository = SQLiteRuntimeRepository(db_path)
    if backup_path is not None:
        repository.backup_to(backup_path)
    errors: list[str] = []
    imported: dict[str, int] = {}
    existing: dict[str, int] = {}
    for namespace, row in _sources(data_dir, errors):
        record_id, partition_key, idempotency_key = _identity(namespace, row)
        if not record_id:
            errors.append(f"{namespace}: record missing stable id")
            continue
        _, created = repository.insert(
            namespace,
            record_id,
            row,
            partition_key=partition_key,
            idempotency_key=idempotency_key,
            created_at=str(row.get("created_at") or row.get("timestamp") or row.get("submitted_at") or ""),
        )
        bucket = imported if created else existing
        bucket[namespace] = bucket.get(namespace, 0) + 1
    healthy, integrity = repository.integrity_check()
    return {
        "status": "ok" if healthy and not errors else "failed",
        "database": str(repository.db_path),
        "backup": str(backup_path.resolve()) if backup_path else None,
        "imported": imported,
        "already_present": existing,
        "errors": errors,
        "integrity_check": integrity,
    }


def export_legacy(db_path: Path, output_dir: Path) -> dict[str, Any]:
    repository = SQLiteRuntimeRepository(db_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    layouts = {
        "audit_events": output_dir / "audit" / "audit_events.jsonl",
        "feedback_events": output_dir / "feedback" / "feedback_events.jsonl",
        "survey_responses": output_dir / "surveys" / "responses.jsonl",
    }
    for namespace, path in layouts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = repository.list(namespace)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        paths.append(str(path))
    for namespace, directory, id_field, suffix in (
        ("conversation_sessions", output_dir / "conversations", "session_id", ".json"),
        ("survey_campaigns", output_dir / "surveys" / "campaigns", "campaign_id", ".json"),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        for row in repository.list(namespace):
            path = directory / f"{row[id_field]}{suffix}"
            path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            paths.append(str(path))
    versions_dir = output_dir / "recommendation_versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    by_session: dict[str, list[dict[str, Any]]] = {}
    for row in repository.list("recommendation_versions"):
        by_session.setdefault(str(row.get("session_id") or "default"), []).append(row)
    for session_id, rows in by_session.items():
        path = versions_dir / f"{session_id}.jsonl"
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        paths.append(str(path))
    return {"status": "ok", "database": str(repository.db_path), "files": paths}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("migrate", "export", "check", "restore"))
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "runtime" / "runtime.db")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "runtime_export")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repository = SQLiteRuntimeRepository(args.database)
    if args.action == "migrate":
        result = migrate(args.data_dir, args.database, args.backup)
    elif args.action == "export":
        result = export_legacy(args.database, args.output_dir)
    elif args.action == "restore":
        if args.backup is None:
            parser.error("restore requires --backup")
        repository.restore_from(args.backup)
        healthy, detail = repository.integrity_check()
        result = {"status": "ok" if healthy else "failed", "integrity_check": detail}
    else:
        healthy, detail = repository.integrity_check()
        result = {"status": "ok" if healthy else "failed", "integrity_check": detail}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
