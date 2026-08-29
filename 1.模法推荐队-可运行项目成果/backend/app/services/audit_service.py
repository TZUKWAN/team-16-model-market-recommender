"""Append-only JSONL audit logging service."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any

from app.schemas.audit import AuditEvent
from app.schemas.auth import UserContext
from app.repositories.runtime_repository import SQLiteRuntimeRepository, get_runtime_repository


class AuditService:
    """Writes and reads compact audit events for critical business actions."""

    def __init__(
        self,
        log_path: Path | None = None,
        repository: SQLiteRuntimeRepository | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parents[3]
        self._default_log_path = base_dir / "data" / "audit" / "audit_events.jsonl"
        self.log_path = log_path or self._default_log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.repository = repository if repository is not None else (
            get_runtime_repository() if log_path is None else None
        )
        self._lock = threading.Lock()

    def _use_sqlite(self) -> bool:
        return self.repository is not None and self.log_path == self._default_log_path

    def record(
        self,
        event_type: str,
        user: UserContext,
        *,
        request_id: str = "",
        model_id: str = "",
        task_id: str = "",
        result_type: str = "",
        status: str = "success",
        payload_summary: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=f"AUD_{uuid.uuid4().hex[:12].upper()}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            user_id=user.user_id,
            role=user.role,
            institution_id=user.institution_id,
            legal_entity_id=user.legal_entity_id,
            request_id=request_id,
            model_id=model_id,
            task_id=task_id,
            result_type=result_type,
            status=status,
            payload_summary=self._compact_summary(payload_summary or {}),
        )
        with self._lock:
            if self._use_sqlite():
                assert self.repository is not None
                self.repository.insert(
                    "audit_events",
                    event.event_id,
                    event.model_dump(),
                    partition_key=event.legal_entity_id or event.institution_id,
                    created_at=event.timestamp,
                )
            else:
                with self.log_path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
        return event

    def query(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
        user_id: str | None = None,
    ) -> list[AuditEvent]:
        events: list[AuditEvent] = []
        if self._use_sqlite():
            assert self.repository is not None
            payloads = self.repository.list("audit_events")
        else:
            if not self.log_path.exists():
                return []
            payloads = []
            with self.log_path.open("r", encoding="utf-8") as file:
                for line in file:
                    try:
                        if line.strip():
                            payloads.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        for payload in payloads:
            try:
                event = AuditEvent(**payload)
            except (TypeError, ValueError):
                continue
            if event_type and event.event_type != event_type:
                continue
            if user_id and event.user_id != user_id:
                continue
            events.append(event)
        return events[-max(1, min(limit, 500)):]

    def _compact_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                compact[key] = value[:160]
            elif isinstance(value, list):
                compact[key] = value[:10]
            elif isinstance(value, dict):
                compact[key] = {
                    str(k): str(v)[:80]
                    for k, v in list(value.items())[:10]
                }
            else:
                compact[key] = value
        return compact


_audit_service = AuditService()


def get_audit_service() -> AuditService:
    return _audit_service
