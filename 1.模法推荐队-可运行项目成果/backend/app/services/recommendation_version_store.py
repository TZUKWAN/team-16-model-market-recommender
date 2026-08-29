"""Persistent recommendation version store.

Each recommendation result is saved as an immutable version keyed by
(session_id, version_id). Versions survive process restarts via file-backed
JSONL storage. This enables cross-session recommendation comparison without
relying on in-memory React state.

Storage: data/recommendation_versions/<session_id>.jsonl
Each line is one version record with full provenance.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.repositories.runtime_repository import SQLiteRuntimeRepository, get_runtime_repository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RecommendationVersionStore:
    """Append-only, idempotent recommendation version store."""

    def __init__(
        self,
        base_dir: Path | None = None,
        repository: SQLiteRuntimeRepository | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[3]
        self._default_storage_dir = project_root / "data" / "recommendation_versions"
        self.storage_dir = base_dir or self._default_storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.repository = repository if repository is not None else (
            get_runtime_repository() if base_dir is None else None
        )
        self._lock = threading.RLock()

    def _use_sqlite(self) -> bool:
        return self.repository is not None and self.storage_dir == self._default_storage_dir

    def _session_path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
        return self.storage_dir / f"{safe_id}.jsonl"

    def save_version(
        self,
        *,
        session_id: str,
        request_id: str,
        parse_summary: dict[str, Any],
        recommendations: list[dict[str, Any]],
        config_hash: str = "",
        raw_text: str = "",
        idempotency_key: str = "",
        owner_user_id: str = "",
        institution_id: str = "",
        legal_entity_id: str = "",
    ) -> dict[str, Any]:
        """Save a recommendation result as a new version.

        Idempotent: if a version with the same request_id already exists for
        this session, it returns the existing version without duplicating.
        """
        stable_key = idempotency_key.strip() or request_id
        sqlite_mode = self._use_sqlite()
        with (nullcontext() if sqlite_mode else self._lock):
            # Keep the read/check/write sequence inside one lock. Otherwise two
            # concurrent JSONL retries can both pass the idempotency check.
            # SQLite performs the same check atomically inside its transaction.
            existing = [] if sqlite_mode else self._read_versions(session_id)
            for record in existing:
                existing_key = record.get("idempotency_key") or record.get("request_id")
                if existing_key == stable_key:
                    return record

            model_ranking = []
            for rec in recommendations[:10]:
                score = rec.get("total_score", 0)
                if not isinstance(score, (int, float)):
                    score = 0
                score_value = float(score)
                if not math.isfinite(score_value):
                    score_value = 0.0
                model_ranking.append({
                    "model_id": str(rec.get("model_id", "")),
                    "model_name": str(rec.get("model_name", "")),
                    "rank": int(rec.get("rank", 0) or 0),
                    "total_score": round(score_value, 2),
                })

            record = {
                "version_id": f"VER_{uuid.uuid4().hex[:12].upper()}",
                "session_id": session_id,
                "request_id": request_id,
                "idempotency_key": stable_key,
                "created_at": _now_iso(),
                "owner_user_id": owner_user_id,
                "institution_id": institution_id,
                "legal_entity_id": legal_entity_id,
                "raw_text_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest()[:16] if raw_text else "",
                "parse_summary": {
                    "intent": parse_summary.get("intent", ""),
                    "business_scenario": parse_summary.get("business_scenario", ""),
                    "business_stage": parse_summary.get("business_stage", ""),
                    "confidence": parse_summary.get("intent_confidence", parse_summary.get("confidence", 0)),
                },
                "model_ranking": model_ranking,
                "config_hash": config_hash,
            }
            if sqlite_mode:
                assert self.repository is not None
                stored, _ = self.repository.insert_with_sequence(
                    "recommendation_versions",
                    record["version_id"],
                    record,
                    partition_key=session_id,
                    sequence_field="version_number",
                    idempotency_key=f"{session_id}:{stable_key}",
                    created_at=record["created_at"],
                )
                return stored

            record["version_number"] = len(existing) + 1
            path = self._session_path(session_id)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    def list_versions(
        self,
        session_id: str,
        *,
        user_id: str = "",
        institution_id: str = "",
        legal_entity_id: str = "",
        can_view_audit: bool = False,
    ) -> list[dict[str, Any]]:
        """Return all versions for a session, ordered by version number."""
        records = self._read_versions(session_id)
        return [
            record for record in records
            if self._can_access(
                record,
                user_id=user_id,
                institution_id=institution_id,
                legal_entity_id=legal_entity_id,
                can_view_audit=can_view_audit,
            )
        ]

    def get_version(
        self,
        session_id: str,
        version_id: str,
        **access: Any,
    ) -> dict[str, Any] | None:
        """Return a single version by ID."""
        for record in self.list_versions(session_id, **access):
            if record.get("version_id") == version_id:
                return record
        return None

    def diff_versions(
        self,
        session_id: str,
        version_a: str,
        version_b: str,
        **access: Any,
    ) -> dict[str, Any]:
        """Compare two recommendation versions.

        Returns added/removed models, rank changes, and score deltas.
        """
        va = self.get_version(session_id, version_a, **access)
        vb = self.get_version(session_id, version_b, **access)
        if va is None or vb is None:
            return {"error": "One or both versions not found", "version_a": version_a, "version_b": version_b}

        models_a = {m["model_id"]: m for m in va.get("model_ranking", [])}
        models_b = {m["model_id"]: m for m in vb.get("model_ranking", [])}

        added = []
        for mid, m in models_b.items():
            if mid not in models_a:
                added.append(mid)

        removed = []
        for mid, m in models_a.items():
            if mid not in models_b:
                removed.append(mid)

        rank_changes = []
        for mid in set(models_a.keys()) & set(models_b.keys()):
            ra = models_a[mid]["rank"]
            rb = models_b[mid]["rank"]
            sa = models_a[mid].get("total_score", 0)
            sb = models_b[mid].get("total_score", 0)
            if ra != rb or abs(sa - sb) > 0.01:
                rank_changes.append({
                    "model_id": mid,
                    "model_name": models_b[mid].get("model_name", ""),
                    "rank_a": ra,
                    "rank_b": rb,
                    "rank_delta": rb - ra,
                    "score_a": sa,
                    "score_b": sb,
                    "score_delta": round(sb - sa, 2),
                })

        return {
            "session_id": session_id,
            "version_a": version_a,
            "version_b": version_b,
            "added_models": added,
            "removed_models": removed,
            "rank_changes": sorted(rank_changes, key=lambda x: x["rank_b"]),
            "summary": f"新增 {len(added)} 个模型，移除 {len(removed)} 个模型，{len(rank_changes)} 个模型排名或分数变化。",
        }

    @staticmethod
    def _can_access(
        record: dict[str, Any],
        *,
        user_id: str,
        institution_id: str,
        legal_entity_id: str,
        can_view_audit: bool,
    ) -> bool:
        # Internal service calls without an access scope remain available for
        # tests and maintenance. API calls always provide a user scope.
        if not any((user_id, institution_id, legal_entity_id, can_view_audit)):
            return True
        record_legal = str(record.get("legal_entity_id", ""))
        if can_view_audit:
            return not legal_entity_id or not record_legal or record_legal == legal_entity_id
        return (
            bool(user_id)
            and record.get("owner_user_id") == user_id
            and record.get("institution_id") == institution_id
            and (not legal_entity_id or not record_legal or record_legal == legal_entity_id)
        )

    def _read_versions(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            if self._use_sqlite():
                assert self.repository is not None
                return self.repository.list("recommendation_versions", partition_key=session_id)
            path = self._session_path(session_id)
            if not path.exists():
                return []
            records: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
            return records

    def clear_session(self, session_id: str) -> int:
        """Delete all versions for a session. Returns the count deleted."""
        with self._lock:
            if self._use_sqlite():
                assert self.repository is not None
                return self.repository.delete_partition("recommendation_versions", session_id)
            path = self._session_path(session_id)
            count = len(self._read_versions(session_id))
            path.unlink(missing_ok=True)
        return count


_store: RecommendationVersionStore | None = None


def get_recommendation_version_store() -> RecommendationVersionStore:
    global _store
    if _store is None:
        _store = RecommendationVersionStore()
    return _store


def recommendation_config_hash() -> str:
    """Return a stable hash of the recommendation configuration."""
    project_root = Path(__file__).resolve().parents[3]
    path = project_root / "data" / "config" / "recommendation_weights.json"
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()
