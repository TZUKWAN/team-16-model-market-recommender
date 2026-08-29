"""Transactional SQLite storage for mutable runtime records."""

from __future__ import annotations

from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Iterator


class SQLiteRuntimeRepository:
    """Small namespaced JSON-record repository with transactional uniqueness."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            root = Path(__file__).resolve().parents[3]
            configured = os.getenv("RUNTIME_DB_PATH", "data/runtime/runtime.db")
            candidate = Path(configured)
            db_path = candidate if candidate.is_absolute() else root / candidate
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._integrity_lock = threading.Lock()
        self._integrity_cached_at = 0.0
        self._integrity_cached_result: tuple[bool, str] = (False, "not_checked")
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_records (
                    namespace TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    partition_key TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
                    PRIMARY KEY(namespace, record_id),
                    UNIQUE(namespace, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_runtime_namespace_partition_created
                    ON runtime_records(namespace, partition_key, created_at, record_id);
                CREATE INDEX IF NOT EXISTS idx_runtime_namespace_created
                    ON runtime_records(namespace, created_at, record_id);
                CREATE INDEX IF NOT EXISTS idx_runtime_feedback_scope
                    ON runtime_records(
                        namespace,
                        json_extract(payload_json, '$.role'),
                        json_extract(payload_json, '$.scenario'),
                        json_extract(payload_json, '$.evidence_mode'),
                        created_at
                    );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(self.SCHEMA_VERSION),),
            )

    @staticmethod
    def _encode(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return json.loads(row["payload_json"]) if row is not None else None

    def insert(
        self,
        namespace: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        partition_key: str = "",
        idempotency_key: str | None = None,
        created_at: str = "",
    ) -> tuple[dict[str, Any], bool]:
        """Insert once; return the existing payload on idempotency conflict."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = connection.execute(
                        "SELECT payload_json FROM runtime_records WHERE namespace=? AND idempotency_key=?",
                        (namespace, idempotency_key),
                    ).fetchone()
                    if existing is not None:
                        connection.commit()
                        decoded = self._decode(existing)
                        assert decoded is not None
                        return decoded, False
                connection.execute(
                    """INSERT INTO runtime_records
                       (namespace, record_id, partition_key, idempotency_key, created_at, payload_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        namespace,
                        record_id,
                        partition_key,
                        idempotency_key,
                        created_at or str(payload.get("created_at") or payload.get("timestamp") or ""),
                        self._encode(payload),
                    ),
                )
                connection.commit()
                return payload, True
            except Exception:
                connection.rollback()
                raise

    def upsert(
        self,
        namespace: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        partition_key: str = "",
        created_at: str = "",
    ) -> None:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """INSERT INTO runtime_records
                       (namespace, record_id, partition_key, created_at, payload_json)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(namespace, record_id) DO UPDATE SET
                         partition_key=excluded.partition_key,
                         created_at=excluded.created_at,
                         payload_json=excluded.payload_json""",
                    (
                        namespace,
                        record_id,
                        partition_key,
                        created_at or str(payload.get("created_at") or payload.get("timestamp") or ""),
                        self._encode(payload),
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def insert_many(self, namespace: str, records: list[dict[str, Any]]) -> int:
        """Insert multiple prepared records in one transaction, ignoring duplicates."""
        if not records:
            return 0
        created = 0
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                for item in records:
                    cursor = connection.execute(
                        """INSERT OR IGNORE INTO runtime_records
                           (namespace, record_id, partition_key, idempotency_key, created_at, payload_json)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            namespace,
                            str(item["record_id"]),
                            str(item.get("partition_key") or ""),
                            item.get("idempotency_key"),
                            str(item.get("created_at") or ""),
                            self._encode(item["payload"]),
                        ),
                    )
                    created += int(cursor.rowcount == 1)
                connection.commit()
                return created
            except Exception:
                connection.rollback()
                raise

    def insert_with_sequence(
        self,
        namespace: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        partition_key: str,
        sequence_field: str,
        idempotency_key: str | None = None,
        created_at: str = "",
    ) -> tuple[dict[str, Any], bool]:
        """Atomically allocate a 1-based sequence inside one partition and insert."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = connection.execute(
                        "SELECT payload_json FROM runtime_records WHERE namespace=? AND idempotency_key=?",
                        (namespace, idempotency_key),
                    ).fetchone()
                    if existing is not None:
                        connection.commit()
                        decoded = self._decode(existing)
                        assert decoded is not None
                        return decoded, False
                sequence = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM runtime_records WHERE namespace=? AND partition_key=?",
                        (namespace, partition_key),
                    ).fetchone()[0]
                ) + 1
                stored = {**payload, sequence_field: sequence}
                connection.execute(
                    """INSERT INTO runtime_records
                       (namespace, record_id, partition_key, idempotency_key, created_at, payload_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        namespace,
                        record_id,
                        partition_key,
                        idempotency_key,
                        created_at or str(payload.get("created_at") or ""),
                        self._encode(stored),
                    ),
                )
                connection.commit()
                return stored, True
            except Exception:
                connection.rollback()
                raise

    def insert_with_partition_limit(
        self,
        namespace: str,
        record_id: str,
        payload: dict[str, Any],
        *,
        partition_key: str,
        idempotency_key: str,
        max_records: int,
        consistent_fields: tuple[str, ...] = (),
        created_at: str = "",
    ) -> tuple[dict[str, Any], bool, int, str]:
        """Atomically validate partition identity/capacity and insert one record.

        The status is one of ``created``, ``duplicate``, ``limit`` or
        ``inconsistent``. This is used for bounded invitation-token submissions
        where process-local locks cannot guarantee correctness.
        """
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT payload_json FROM runtime_records WHERE namespace=? AND idempotency_key=?",
                    (namespace, idempotency_key),
                ).fetchone()
                partition_rows = connection.execute(
                    "SELECT payload_json FROM runtime_records WHERE namespace=? AND partition_key=?",
                    (namespace, partition_key),
                ).fetchall()
                partition_payloads = [json.loads(row["payload_json"]) for row in partition_rows]
                partition_count = len(partition_payloads)
                if existing is not None:
                    decoded = self._decode(existing)
                    assert decoded is not None
                    connection.commit()
                    return decoded, False, partition_count, "duplicate"
                if any(
                    row.get(field) != payload.get(field)
                    for row in partition_payloads
                    for field in consistent_fields
                ):
                    connection.commit()
                    return payload, False, partition_count, "inconsistent"
                if partition_count >= max(1, int(max_records)):
                    connection.commit()
                    return payload, False, partition_count, "limit"
                connection.execute(
                    """INSERT INTO runtime_records
                       (namespace, record_id, partition_key, idempotency_key, created_at, payload_json)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        namespace,
                        record_id,
                        partition_key,
                        idempotency_key,
                        created_at or str(payload.get("created_at") or payload.get("submitted_at") or ""),
                        self._encode(payload),
                    ),
                )
                connection.commit()
                return payload, True, partition_count + 1, "created"
            except Exception:
                connection.rollback()
                raise

    def get(self, namespace: str, record_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM runtime_records WHERE namespace=? AND record_id=?",
                (namespace, record_id),
            ).fetchone()
        return self._decode(row)

    def list(
        self,
        namespace: str,
        *,
        partition_key: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT payload_json FROM runtime_records WHERE namespace=?"
        params: list[Any] = [namespace]
        if partition_key is not None:
            query += " AND partition_key=?"
            params.append(partition_key)
        query += " ORDER BY created_at ASC, record_id ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(max(1, int(limit)))
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def list_by_json_fields(
        self,
        namespace: str,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Filter indexed JSON scalar fields without interpolating untrusted paths."""
        query = "SELECT payload_json FROM runtime_records WHERE namespace=?"
        params: list[Any] = [namespace]
        for field, value in filters.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field):
                raise ValueError(f"invalid JSON field: {field}")
            query += f" AND json_extract(payload_json, '$.{field}')=?"
            params.append(value)
        query += " ORDER BY created_at ASC, record_id ASC"
        with self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def delete_partition(self, namespace: str, partition_key: str) -> int:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    "DELETE FROM runtime_records WHERE namespace=? AND partition_key=?",
                    (namespace, partition_key),
                )
                connection.commit()
                return int(cursor.rowcount)
            except Exception:
                connection.rollback()
                raise

    def count(self, namespace: str, *, partition_key: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM runtime_records WHERE namespace=?"
        params: list[Any] = [namespace]
        if partition_key is not None:
            query += " AND partition_key=?"
            params.append(partition_key)
        with self._connection() as connection:
            return int(connection.execute(query, params).fetchone()[0])

    def integrity_check(self, *, cache_ttl_seconds: float = 0.0) -> tuple[bool, str]:
        now = time.monotonic()
        with self._integrity_lock:
            if cache_ttl_seconds > 0 and now - self._integrity_cached_at < cache_ttl_seconds:
                return self._integrity_cached_result
            try:
                with self._connection() as connection:
                    result = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                checked = (result.lower() == "ok", result)
            except sqlite3.DatabaseError as exc:
                checked = (False, str(exc))
            self._integrity_cached_at = now
            self._integrity_cached_result = checked
            return checked

    def backup_to(self, destination: Path | str) -> Path:
        destination_path = Path(destination).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination_path.with_suffix(destination_path.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        with self._connection() as source:
            with closing(sqlite3.connect(temporary)) as target:
                source.backup(target)
        temporary.replace(destination_path)
        return destination_path

    def restore_from(self, source: Path | str) -> None:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        with closing(sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)) as check:
            result = str(check.execute("PRAGMA integrity_check").fetchone()[0])
            if result.lower() != "ok":
                raise sqlite3.DatabaseError(f"backup integrity check failed: {result}")
        temporary = self.db_path.with_suffix(self.db_path.suffix + ".restore.tmp")
        temporary.unlink(missing_ok=True)
        with closing(sqlite3.connect(source_path)) as backup:
            with closing(sqlite3.connect(temporary)) as target:
                backup.backup(target)
        with self._connection() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        temporary.replace(self.db_path)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)
        self._initialize()


_runtime_repository: SQLiteRuntimeRepository | None = None


def get_runtime_repository() -> SQLiteRuntimeRepository:
    global _runtime_repository
    if _runtime_repository is None:
        _runtime_repository = SQLiteRuntimeRepository()
    return _runtime_repository
