"""Append-only feedback service for recommendation adoption loops."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid
from typing import Any

from app.schemas.auth import UserContext
from app.schemas.feedback import FeedbackEvent, ModelFeedbackStats
from app.repositories.runtime_repository import SQLiteRuntimeRepository, get_runtime_repository


class FeedbackService:
    """Record recommendation impressions and explicit user feedback."""

    def __init__(
        self,
        log_path: Path | None = None,
        repository: SQLiteRuntimeRepository | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parents[3]
        self._default_log_path = base_dir / "data" / "feedback" / "feedback_events.jsonl"
        self.log_path = log_path or self._default_log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.repository = repository if repository is not None else (
            get_runtime_repository() if log_path is None else None
        )
        self._lock = threading.Lock()

    def _use_sqlite(self) -> bool:
        return self.repository is not None and self.log_path == self._default_log_path

    def record_feedback(
        self,
        user: UserContext,
        *,
        request_id: str,
        model_id: str,
        model_name: str = "",
        action: str,
        reason: str = "",
        scenario: str = "",
        metadata: dict[str, Any] | None = None,
        evidence_mode: str = "human",
    ) -> FeedbackEvent:
        event = self._build_event(
            user,
            request_id=request_id,
            model_id=model_id,
            model_name=model_name,
            action=action,
            reason=reason,
            scenario=scenario,
            metadata=metadata or {},
            evidence_mode=evidence_mode,
        )
        self._append(event)
        return event

    def record_recommendation_impressions(
        self,
        user: UserContext,
        *,
        request_id: str,
        parse_result: dict[str, Any],
        recommendations: list[dict[str, Any]],
        evidence_mode: str = "human",
    ) -> None:
        """Record one 'recommended' event per unique (request_id, model_id).

        Idempotent: if impressions for this request_id already exist, they are not
        re-appended. This prevents page refresh / API retry from inflating counts.
        """
        if self._use_sqlite():
            assert self.repository is not None
            scenario = self._scenario(parse_result)
            events = [
                self._build_event(
                    user,
                    request_id=request_id,
                    model_id=str(item.get("model_id", "")),
                    model_name=str(item.get("model_name", "")),
                    action="recommended",
                    scenario=scenario,
                    metadata={"rank": item.get("rank", 0)},
                    evidence_mode=evidence_mode,
                )
                for item in recommendations
            ]
            self.repository.insert_many(
                "feedback_events",
                [
                    {
                        "record_id": event.event_id,
                        "partition_key": event.request_id,
                        "idempotency_key": f"{event.evidence_mode}:{event.request_id}:{event.model_id}:recommended",
                        "created_at": event.timestamp,
                        "payload": event.model_dump(),
                    }
                    for event in events
                ],
            )
            return

        existing = self._read_events()
        already_recorded = {
            (e.request_id, e.model_id)
            for e in existing
            if e.request_id == request_id and e.action == "recommended"
        }
        scenario = self._scenario(parse_result)
        for item in recommendations:
            model_id = str(item.get("model_id", ""))
            if (request_id, model_id) in already_recorded:
                continue
            event = self._build_event(
                user,
                request_id=request_id,
                model_id=model_id,
                model_name=str(item.get("model_name", "")),
                action="recommended",
                scenario=scenario,
                metadata={"rank": item.get("rank", 0)},
                evidence_mode=evidence_mode,
            )
            self._append(event)

    def stats(
        self,
        *,
        scenario: str = "",
        role: str = "",
        limit: int = 100,
        evidence_mode: str = "",
    ) -> tuple[list[ModelFeedbackStats], dict[str, int]]:
        """Compute idempotent stats from the final state of each unique recommendation.

        For each unique (request_id, model_id), only the latest non-'recommended'
        action (adopt/reject/favorite) counts. 'recommended' impressions are counted
        once per unique (request_id, model_id) pair.
        """
        events = self._read_events()
        mode_counts = {"human": 0, "demo": 0, "test": 0}

        # Determine the final user action per (request_id, model_id).
        final_action: dict[tuple[str, str], str] = {}
        for event in events:
            mode_counts[event.evidence_mode] = mode_counts.get(event.evidence_mode, 0) + 1
            if event.action != "recommended":
                key = (event.request_id, event.model_id)
                # Last write wins (events are in chronological append order).
                final_action[key] = event.action

        # Count unique recommended impressions and final actions per (model, scenario).
        recommended_keys: dict[tuple[str, str], set[str]] = {}
        event_meta: dict[tuple[str, str], dict[str, str]] = {}
        final_counts: dict[tuple[str, str], dict[str, int]] = {}

        for event in events:
            if scenario and event.scenario != scenario:
                continue
            if role and event.role != role:
                continue
            if evidence_mode and event.evidence_mode != evidence_mode:
                continue
            key = (event.model_id, event.scenario)
            event_meta.setdefault(key, {"model_name": event.model_name})
            if event.model_name and not event_meta[key]["model_name"]:
                event_meta[key]["model_name"] = event.model_name

            if event.action == "recommended":
                recommended_keys.setdefault(key, set()).add(event.request_id)
            elif event.action in ("adopt", "reject", "favorite"):
                # Only count the final action for this (request_id, model_id).
                rec_key = (event.request_id, event.model_id)
                if final_action.get(rec_key) == event.action:
                    final_counts.setdefault(key, {"adopt": 0, "reject": 0, "favorite": 0})
                    final_counts[key][event.action] = final_counts[key].get(event.action, 0) + 1

        buckets: dict[tuple[str, str], ModelFeedbackStats] = {}
        all_keys = set(recommended_keys.keys()) | set(final_counts.keys())
        for key in all_keys:
            model_id, scen = key
            rec_count = len(recommended_keys.get(key, set()))
            fc = final_counts.get(key, {"adopt": 0, "reject": 0, "favorite": 0})
            stat = ModelFeedbackStats(
                model_id=model_id,
                model_name=event_meta.get(key, {}).get("model_name", ""),
                scenario=scen,
                recommended_count=rec_count,
                adopt_count=fc.get("adopt", 0),
                reject_count=fc.get("reject", 0),
                favorite_count=fc.get("favorite", 0),
            )
            denominator = stat.recommended_count or (stat.adopt_count + stat.reject_count + stat.favorite_count)
            stat.adoption_rate = round(stat.adopt_count / denominator, 4) if denominator else 0.0
            buckets[key] = stat

        items = list(buckets.values())
        items.sort(key=lambda s: (-s.adoption_rate, -s.adopt_count, s.model_id))
        return items[: max(1, min(limit, 500))], mode_counts

    def model_adoption_rate(
        self,
        *,
        model_id: str,
        role: str,
        scenario: str,
        min_recommendations: int = 5,
    ) -> dict[str, Any]:
        """Compute adoption rate from human-mode unique recommendations only.

        Demo/test feedback never affects production ranking.
        """
        events = self._read_events(role=role, scenario=scenario, evidence_mode="human")
        recommended_request_ids: set[str] = set()
        adopted_request_ids: set[str] = set()
        final_action: dict[str, str] = {}

        for event in events:
            if event.model_id != model_id:
                continue
            if event.evidence_mode != "human":
                continue
            if role and event.role != role:
                continue
            if scenario and event.scenario != scenario:
                continue
            if event.action == "recommended":
                recommended_request_ids.add(event.request_id)
            elif event.action in ("adopt", "reject", "favorite"):
                final_action[event.request_id] = event.action

        for rid, action in final_action.items():
            if action == "adopt":
                adopted_request_ids.add(rid)

        recommended = len(recommended_request_ids)
        adopted = len(adopted_request_ids)
        if recommended < min_recommendations:
            return {"recommendation_count": recommended, "adopt_count": adopted, "adoption_rate": 0.0, "boost_eligible": False}
        rate = round(adopted / recommended, 4) if recommended else 0.0
        return {"recommendation_count": recommended, "adopt_count": adopted, "adoption_rate": rate, "boost_eligible": True}

    def adoption_rates(
        self,
        *,
        role: str,
        scenario: str,
        min_recommendations: int = 5,
    ) -> dict[str, dict[str, Any]]:
        """Build all model adoption rates from one consistent event snapshot."""
        recommended: dict[str, set[str]] = {}
        final_actions: dict[tuple[str, str], str] = {}
        for event in self._read_events(role=role, scenario=scenario, evidence_mode="human"):
            if event.evidence_mode != "human":
                continue
            if role and event.role != role:
                continue
            if scenario and event.scenario != scenario:
                continue
            if event.action == "recommended":
                recommended.setdefault(event.model_id, set()).add(event.request_id)
            elif event.action in ("adopt", "reject", "favorite"):
                final_actions[(event.model_id, event.request_id)] = event.action

        result: dict[str, dict[str, Any]] = {}
        model_ids = set(recommended) | {model_id for model_id, _ in final_actions}
        for model_id in model_ids:
            recommendation_count = len(recommended.get(model_id, set()))
            adopt_count = sum(
                action == "adopt"
                for (action_model_id, _), action in final_actions.items()
                if action_model_id == model_id
            )
            eligible = recommendation_count >= min_recommendations
            result[model_id] = {
                "recommendation_count": recommendation_count,
                "adopt_count": adopt_count,
                "adoption_rate": round(adopt_count / recommendation_count, 4)
                if eligible and recommendation_count
                else 0.0,
                "boost_eligible": eligible,
            }
        return result

    def total_events(self) -> int:
        return len(self._read_events())

    def mode_counts(self) -> dict[str, int]:
        counts = {"human": 0, "demo": 0, "test": 0}
        for event in self._read_events():
            counts[event.evidence_mode] = counts.get(event.evidence_mode, 0) + 1
        return counts

    def _build_event(
        self,
        user: UserContext,
        *,
        request_id: str,
        model_id: str,
        action: str,
        model_name: str = "",
        reason: str = "",
        scenario: str = "",
        metadata: dict[str, Any] | None = None,
        evidence_mode: str = "human",
    ) -> FeedbackEvent:
        return FeedbackEvent(
            event_id=f"FDB_{uuid.uuid4().hex[:12].upper()}",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            user_id=user.user_id,
            role=user.role,
            institution_id=user.institution_id,
            request_id=request_id,
            model_id=model_id,
            model_name=model_name,
            scenario=scenario,
            action=action,  # type: ignore[arg-type]
            reason=reason[:300],
            metadata=self._compact(metadata or {}),
            evidence_mode=evidence_mode,  # type: ignore[arg-type]
        )

    def _append(self, event: FeedbackEvent) -> None:
        with self._lock:
            if self._use_sqlite():
                assert self.repository is not None
                idempotency_key = None
                if event.action == "recommended":
                    idempotency_key = (
                        f"{event.evidence_mode}:{event.request_id}:{event.model_id}:recommended"
                    )
                self.repository.insert(
                    "feedback_events",
                    event.event_id,
                    event.model_dump(),
                    partition_key=event.request_id,
                    idempotency_key=idempotency_key,
                    created_at=event.timestamp,
                )
            else:
                with self.log_path.open("a", encoding="utf-8") as file:
                    file.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")

    def _read_events(
        self,
        *,
        role: str = "",
        scenario: str = "",
        evidence_mode: str = "",
    ) -> list[FeedbackEvent]:
        if self._use_sqlite():
            assert self.repository is not None
            filters = {
                key: value
                for key, value in {
                    "role": role,
                    "scenario": scenario,
                    "evidence_mode": evidence_mode,
                }.items()
                if value
            }
            payloads = self.repository.list_by_json_fields("feedback_events", filters)
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
        events: list[FeedbackEvent] = []
        for payload in payloads:
            try:
                events.append(FeedbackEvent(**payload))
            except (TypeError, ValueError):
                continue
        return events

    def _scenario(self, parse_result: dict[str, Any]) -> str:
        return str(
            parse_result.get("business_scenario")
            or parse_result.get("scenario")
            or parse_result.get("intent")
            or "unknown"
        )[:120]

    def _compact(self, data: dict[str, Any]) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                compact[key] = value[:160]
            elif isinstance(value, (int, float, bool)):
                compact[key] = value
            elif isinstance(value, list):
                compact[key] = value[:8]
            else:
                compact[key] = str(value)[:160]
        return compact


_feedback_service = FeedbackService()


def get_feedback_service() -> FeedbackService:
    return _feedback_service
