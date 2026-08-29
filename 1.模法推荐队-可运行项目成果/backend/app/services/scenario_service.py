"""Scenario library loader and demand-to-scenario matcher.

Rule-based matching only — no LLM required for matching, keeping it fast,
deterministic and explainable. LLM is used only for script generation
(see script_generator.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.schemas.scenario import (
    BusinessScenario,
    ScenarioMatchItem,
    ScenarioMatchResponse,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[3]
SCENARIO_PATH = BASE_DIR / "data" / "scenarios" / "business_scenarios.jsonl"

# Map intent/domain aliases to canonical scenario domains.
DOMAIN_ALIASES: dict[str, str] = {
    "credit_risk": "credit_risk",
    "risk": "credit_risk",
    "风控": "credit_risk",
    "customer_marketing": "customer_marketing",
    "marketing": "customer_marketing",
    "营销": "customer_marketing",
    "operation_management": "operation_management",
    "operation": "operation_management",
    "运营": "operation_management",
}

_scenarios_cache: list[BusinessScenario] | None = None


def load_scenarios() -> list[BusinessScenario]:
    """Load the business scenario library (cached after first load)."""
    global _scenarios_cache
    if _scenarios_cache is not None:
        return _scenarios_cache
    scenarios: list[BusinessScenario] = []
    if SCENARIO_PATH.exists():
        for line in SCENARIO_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                scenarios.append(BusinessScenario(**json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.warning("Skipping invalid scenario line")
                continue
    _scenarios_cache = scenarios
    logger.info("Loaded %d business scenarios from %s", len(scenarios), SCENARIO_PATH)
    return scenarios


def _canonical_domain(value: str) -> str:
    """Resolve an intent/domain string to a canonical scenario domain."""
    if not value:
        return ""
    key = value.lower().strip()
    return DOMAIN_ALIASES.get(key, value)


class ScenarioService:
    """Match parsed demands to business scenarios via rules."""

    def match(self, parse_result: dict[str, Any], top_k: int = 3) -> ScenarioMatchResponse:
        scenarios = load_scenarios()
        raw_text = str(
            parse_result.get("raw_text")
            or parse_result.get("normalized_query")
            or ""
        )
        scenario_text = str(
            parse_result.get("business_scenario")
            or parse_result.get("scenario")
            or ""
        )
        intent = str(
            parse_result.get("intent")
            or parse_result.get("domain")
            or ""
        )
        canonical_intent = _canonical_domain(intent)
        combined_text = f"{raw_text} {scenario_text}"

        matches: list[ScenarioMatchItem] = []
        for sc in scenarios:
            score = 0.0
            matched_kw: list[str] = []

            # Domain match — strongest signal
            if canonical_intent and sc.domain and canonical_intent == sc.domain:
                score += 30.0

            # Keyword hits in raw text / scenario text
            for kw in sc.keywords:
                if kw and kw in combined_text:
                    score += 10.0
                    matched_kw.append(kw)

            # Name overlap — partial credit for scenario name fragments
            if sc.name:
                name_fragment = sc.name[:4]
                if any(ch in raw_text for ch in name_fragment if len(ch) > 1):
                    score += 5.0

            # Business stage signal
            stage = str(parse_result.get("business_stage") or "")
            if stage and sc.business_stage and stage == sc.business_stage:
                score += 8.0

            # Only include scenarios with some signal, or all if nothing matched
            if score > 0:
                matches.append(
                    ScenarioMatchItem(
                        scenario=sc,
                        match_score=round(score, 1),
                        matched_keywords=matched_kw,
                        match_reason=self._reason(score, matched_kw, canonical_intent, sc.domain),
                    )
                )

        matches.sort(key=lambda m: (-m.match_score, m.scenario.scenario_id))

        # Fallback: if nothing matched, return top scenarios by domain proximity
        if not matches and scenarios:
            matches = [
                ScenarioMatchItem(
                    scenario=sc,
                    match_score=0.0,
                    matched_keywords=[],
                    match_reason="无明确匹配信号，按场景库顺序返回候选",
                )
                for sc in scenarios[:top_k]
            ]

        limited = matches[: max(1, min(top_k, len(matches)))]
        return ScenarioMatchResponse(matches=limited, total_scenarios=len(scenarios))

    def get_scenario(self, scenario_id: str) -> BusinessScenario | None:
        for sc in load_scenarios():
            if sc.scenario_id == scenario_id:
                return sc
        return None

    def list_scenarios(self, domain: str = "") -> list[BusinessScenario]:
        scenarios = load_scenarios()
        if not domain:
            return scenarios
        canonical = _canonical_domain(domain)
        return [sc for sc in scenarios if sc.domain == canonical]

    @staticmethod
    def _reason(
        _score: float,
        matched_keywords: list[str],
        intent_domain: str,
        scenario_domain: str,
    ) -> str:
        parts: list[str] = []
        if intent_domain and scenario_domain and intent_domain == scenario_domain:
            parts.append(f"业务领域匹配({scenario_domain})")
        if matched_keywords:
            parts.append(f"关键词命中[{', '.join(matched_keywords[:5])}]")
        if not parts:
            parts.append("无明确关键词命中，按业务领域与场景库顺序返回候选")
        return "；".join(parts)


_scenario_service = ScenarioService()


def get_scenario_service() -> ScenarioService:
    return _scenario_service
