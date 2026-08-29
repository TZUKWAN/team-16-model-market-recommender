"""
official_recommender.py — Lightweight recommendation engine for OFFICIAL_* models.

Keyword-overlap scoring with synonym expansion.
No external API calls, no additional pip dependencies.
"""

from __future__ import annotations
import json
import re
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Chinese stopwords (too generic in banking context) ─────────
_STOPWORDS: frozenset[str] = frozenset({
    "的", "和", "与", "或", "在", "对", "为", "以", "等",
    "基于", "进行", "通过", "利用", "实现", "提供", "支持", "包括",
    "模型", "业务", "客户", "数据", "分析", "系统", "管理",
})

# ─── Character class regexes ───────────────────────────────────
_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]+")
_EN_NUM_RE = re.compile(r"[a-zA-Z0-9]+")

# ─── Punctuation chars replaced with space ─────────────────────
_PUNCTUATION = ",，。、;；/|()（）[]【】"


class OfficialRecommender:
    """
    Lightweight model recommender operating solely on OFFICIAL_* models.

    Uses keyword overlap scoring (with synonym expansion) across
    model_name, description, business_scenario, and tags.
    """

    def __init__(self):
        project_root = Path(__file__).resolve().parent.parent.parent.parent

        # 1. Load the 60 OFFICIAL models ──────────────────────────
        models_path = project_root / "data" / "official_60" / "models.jsonl"
        if not models_path.exists():
            raise FileNotFoundError(
                f"OFFICIAL models file not found: {models_path}"
            )

        self.models: list[dict[str, Any]] = []
        self.model_by_id: dict[str, dict[str, Any]] = {}
        with open(models_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    m = json.loads(line)
                    self.models.append(m)
                    self.model_by_id[m["model_id"]] = m

        if len(self.models) != 60:
            raise ValueError(
                f"Expected exactly 60 OFFICIAL models, got {len(self.models)}"
            )

        # Validate model_id constraints
        for m in self.models:
            mid = m["model_id"]
            if not mid.startswith("OFFICIAL_"):
                raise ValueError(
                    f"Model {mid} does not start with OFFICIAL_"
                )
            if mid.startswith("RISK_") or mid.startswith("MKT_") or mid.startswith("OPS_"):
                raise ValueError(
                    f"Model {mid} has a legacy prefix (RISK_/MKT_/OPS_)"
                )

        # 2. Load synonyms ────────────────────────────────────────
        synonyms_path = project_root / "data" / "config" / "synonyms.json"
        self.synonym_map: dict[str, list[str]] = {}
        self._reverse_synonym_map: dict[str, set[str]] = {}
        if synonyms_path.exists():
            with open(synonyms_path, "r", encoding="utf-8") as f:
                self.synonym_map = json.load(f)
            # Build reverse map: synonym_value -> {keys that map to it}
            for key, syns in self.synonym_map.items():
                for syn in syns:
                    self._reverse_synonym_map.setdefault(syn, set()).add(key)

        logger.info(
            "OfficialRecommender initialized with %d models, %d synonym keys",
            len(self.models),
            len(self.synonym_map),
        )

    # ─── Public API ──────────────────────────────────────────────

    def recommend(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Return top-K OFFICIAL model recommendations for *query*.

        Returns
        -------
        list[dict]
            Each dict: model_id, model_name, score, matched_keywords, source_type.
        """
        query_tokens = self._extract_tokens(query)
        expanded_tokens = self._expand_synonyms(query_tokens)

        scored: list[tuple[dict[str, Any], float, set[str]]] = []
        for model in self.models:
            score, matched = self._score_model(model, query_tokens, expanded_tokens)
            scored.append((model, score, matched))

        # Sort by score desc → model_id asc
        scored.sort(key=lambda x: (-x[1], x[0]["model_id"]))

        results = []
        for model, score, matched in scored[:top_k]:
            direct_matches = query_tokens & matched
            synonym_only = matched - direct_matches
            # Direct before synonyms, then alphabetically
            ordered = sorted(direct_matches) + sorted(synonym_only)
            results.append({
                "model_id": model["model_id"],
                "model_name": model["model_name"],
                "score": round(float(score), 1),
                "matched_keywords": ordered[:8],
                "source_type": "official_dataset",
            })

        return results

    def get_model_by_id(self, model_id: str) -> dict[str, Any] | None:
        """Look up a model by its ID; returns None if not found."""
        return self.model_by_id.get(model_id)

    def list_model_ids(self) -> list[str]:
        """Return all OFFICIAL model IDs in order."""
        return [m["model_id"] for m in self.models]

    # ─── Tokenization ───────────────────────────────────────────

    def _extract_tokens(self, text: str) -> set[str]:
        """
        Extract meaningful tokens from *text*.

        *  Chinese: contiguous character bigrams (length == 2)
        *  English/number words (length >= 2), split by ``_``
        *  Stopwords removed
        """
        if not text:
            return set()

        text = text.lower().strip()

        # Remove punctuation
        for ch in _PUNCTUATION:
            text = text.replace(ch, " ")

        tokens: set[str] = set()

        # Chinese: all contiguous 2-char substrings from each sequence
        for seq in _CHINESE_RE.findall(text):
            if len(seq) < 2:
                continue
            for i in range(len(seq) - 1):
                bigram = seq[i : i + 2]
                if bigram not in _STOPWORDS:
                    tokens.add(bigram)

        # English / number words
        for word in _EN_NUM_RE.findall(text):
            if len(word) >= 2 and word not in _STOPWORDS:
                tokens.add(word)
                for sub in word.split("_"):
                    if len(sub) >= 2 and sub not in _STOPWORDS:
                        tokens.add(sub)

        return tokens

    def _expand_synonyms(self, tokens: set[str]) -> set[str]:
        """
        Bidirectional synonym expansion.

        *  If *token* is a key in synonyms.json → add its synonym list.
        *  If *token* appears as a value in any list → add the key +
           all other synonyms of that key.
        """
        expanded = set(tokens)

        for token in tokens:
            # Forward: token is a key
            if token in self.synonym_map:
                expanded.update(self.synonym_map[token])
            # Reverse: token is a synonym value
            if token in self._reverse_synonym_map:
                for key in self._reverse_synonym_map[token]:
                    expanded.add(key)
                    if key in self.synonym_map:
                        expanded.update(self.synonym_map[key])

        return expanded

    # ─── Scoring ────────────────────────────────────────────────

    def _get_model_text(self, model: dict[str, Any]) -> str:
        """Build concatenated search text for a model."""
        parts: list[str] = [
            model.get("model_name", ""),
            model.get("description", ""),
            model.get("business_scenario", ""),
        ]
        tags = model.get("tags", [])
        if isinstance(tags, list):
            parts.extend(tags)
        return " ".join(str(p) for p in parts if p)

    def _score_model(
        self,
        model: dict[str, Any],
        query_tokens: set[str],
        expanded_tokens: set[str],
    ) -> tuple[float, set[str]]:
        """
        Score one model against query tokens.

        Returns (score, matched_keywords_set).
        """
        model_text = self._get_model_text(model)
        model_tokens = self._extract_tokens(model_text)

        # Direct matches: original query tokens found in model text
        direct_matches = query_tokens & model_tokens

        # Synonym matches: expanded-but-not-original tokens found in model text
        synonym_matches = (expanded_tokens - query_tokens) & model_tokens

        # Raw score
        score_raw = len(direct_matches) * 1.0 + len(synonym_matches) * 0.5

        # Name-substring bonus
        model_name = model.get("model_name", "")
        for token in query_tokens:
            if token in model_name:
                score_raw += 1.0
                break

        # Normalise to 0–100
        n_query = max(len(query_tokens), 1)
        score = min(100.0, score_raw / n_query * 30.0)

        matched = direct_matches | synonym_matches
        return score, matched
