"""Cached, durable conversation session store for multi-turn clarification.

Previously the "multi-turn clarification" was stateless: the API just concatenated
the user's clarification answers back onto the raw text and re-parsed from
scratch (see parse_demand.py::_enrich_text_with_clarification). The parser's
``context`` argument was never read, and ``clarification_round`` was a
front-end-only heuristic.

This store gives each demand conversation a persistent identity so that:
  - the parser can see the full Q&A history when deciding what to ask next,
  - the front-end round counter reflects real backend state,
  - a conversation can converge (stop asking) once enough slots are filled.

Sessions are cached in memory for low latency and stored in the shared runtime
SQLite database. Explicit ``conversations_dir`` instances retain the legacy JSON
backend for import compatibility and isolated tests.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.repositories.runtime_repository import SQLiteRuntimeRepository, get_runtime_repository


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationTurn:
    """One round of user input + the clarification questions it produced."""

    def __init__(
        self,
        turn_id: str,
        raw_text: str,
        asked_questions: list[dict[str, Any]] | None = None,
        answers: list[dict[str, Any]] | None = None,
        parse_source: str = "",
        created_at: str = "",
    ) -> None:
        self.turn_id = turn_id
        self.raw_text = raw_text
        self.asked_questions = asked_questions or []
        self.answers = answers or []
        self.parse_source = parse_source
        self.created_at = created_at or _now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "raw_text": self.raw_text,
            "asked_questions": self.asked_questions,
            "answers": self.answers,
            "parse_source": self.parse_source,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationTurn":
        return cls(
            turn_id=data.get("turn_id", ""),
            raw_text=data.get("raw_text", ""),
            asked_questions=data.get("asked_questions", []),
            answers=data.get("answers", []),
            parse_source=data.get("parse_source", ""),
            created_at=data.get("created_at", ""),
        )


class ConversationSession:
    """A multi-turn demand clarification conversation."""

    MAX_TURNS = 3  # convergence cap: stop asking after this many rounds

    def __init__(
        self,
        session_id: str,
        original_demand: str = "",
        created_at: str = "",
    ) -> None:
        self.session_id = session_id
        self.original_demand = original_demand
        self.turns: list[ConversationTurn] = []
        self.created_at = created_at or _now_iso()
        self.converged: bool = False

    @property
    def round_number(self) -> int:
        """1-based current round (turns already started + 1, capped)."""
        return min(len(self.turns) + 1, self.MAX_TURNS)

    def add_turn(self, turn: ConversationTurn) -> None:
        self.turns.append(turn)
        if len(self.turns) >= self.MAX_TURNS:
            self.converged = True

    def mark_converged(self) -> None:
        self.converged = True

    @property
    def history_qa(self) -> list[dict[str, Any]]:
        """Flattened Q&A history across all turns, for the LLM prompt."""
        qa: list[dict[str, Any]] = []
        for turn in self.turns:
            for ans in turn.answers:
                qa.append({
                    "question": ans.get("question_text", ""),
                    "answer": ans.get("user_answer", ""),
                    "slot": ans.get("slot", ""),
                })
        return qa

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "original_demand": self.original_demand,
            "turns": [t.to_dict() for t in self.turns],
            "created_at": self.created_at,
            "converged": self.converged,
            "round_number": self.round_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationSession":
        sess = cls(
            session_id=data.get("session_id", ""),
            original_demand=data.get("original_demand", ""),
            created_at=data.get("created_at", ""),
        )
        sess.turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
        sess.converged = data.get("converged", False)
        return sess


class ConversationStore:
    """Thread-safe cached conversation store with durable persistence.

    Sessions live in a module-level singleton so all requests (and tests) share
    state. Default instances persist to SQLite; explicit directories use JSON.
    """

    _instance: "ConversationStore | None" = None
    _lock = threading.Lock()

    def __init__(
        self,
        conversations_dir: Path | None = None,
        repository: SQLiteRuntimeRepository | None = None,
    ) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        self._default_conversations_dir = settings.DATA_DIR / "conversations"
        self.conversations_dir = conversations_dir or self._default_conversations_dir
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.repository = repository if repository is not None else (
            get_runtime_repository() if conversations_dir is None else None
        )
        self._sessions: dict[str, ConversationSession] = {}
        self._cache_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ConversationStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def new_session(self, original_demand: str = "") -> ConversationSession:
        session_id = f"conv_{uuid.uuid4().hex[:12]}"
        session = ConversationSession(session_id=session_id, original_demand=original_demand)
        with self._cache_lock:
            self._sessions[session_id] = session
        self._persist(session)
        return session

    def get_session(self, session_id: str) -> ConversationSession | None:
        if not session_id:
            return None
        with self._cache_lock:
            session = self._sessions.get(session_id)
        if session is not None:
            return session
        # Try loading from disk (e.g. after a process restart).
        return self._load(session_id)

    def save(self, session: ConversationSession) -> None:
        with self._cache_lock:
            self._sessions[session.session_id] = session
        self._persist(session)

    def _persist(self, session: ConversationSession) -> None:
        payload = session.to_dict()
        if self.repository is not None:
            self.repository.upsert(
                "conversation_sessions",
                session.session_id,
                payload,
                partition_key=session.session_id,
                created_at=session.created_at,
            )
            return
        path = self.conversations_dir / f"{session.session_id}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self, session_id: str) -> ConversationSession | None:
        try:
            if self.repository is not None:
                data = self.repository.get("conversation_sessions", session_id)
                if data is None:
                    return None
            else:
                path = self.conversations_dir / f"{session_id}.json"
                if not path.exists():
                    return None
                data = json.loads(path.read_text(encoding="utf-8"))
            session = ConversationSession.from_dict(data)
            with self._cache_lock:
                self._sessions[session_id] = session
            return session
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None


def get_conversation_store() -> ConversationStore:
    """Module-level accessor used by the API layer."""
    return ConversationStore.get_instance()
