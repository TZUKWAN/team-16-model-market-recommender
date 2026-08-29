"""
recommender.py — Model recommendation engine.

Rule-based recall, multi-dimension scoring, ranking,
evidence generation, data gap analysis, alternative models.
When LLM is available, uses LLM for semantic reranking.
"""

from __future__ import annotations
import json
import uuid
import logging
import os
import hashlib
import re
import threading
import time
from pathlib import Path
from typing import Any

from app.schemas.recommendation import (
    RecommendModelsResponse, RecommendedModel, ScoreBreakdown,
    EvidenceCard, AlternativeModel, UnrecommendedExample,
)
from app.services.data_loader import load_tags, load_data_fields, build_synonym_map
from app.services.llm_client import get_llm_client
from app.services.explanation_generator import ExplanationGenerator
from app.services.data_readiness_service import DataReadinessService
from app.repositories.model_asset_repository import get_model_asset_repository
from app.services.knowledge_graph import get_knowledge_graph_service
from app.services.hybrid_retriever import HybridModelRetriever, HybridRetrievalScore

logger = logging.getLogger(__name__)

# ─── Scoring weights (exact from spec) ─────────────────────────
W_SCENARIO = 0.25
W_CUSTOMER = 0.15
W_DATA = 0.20
W_OUTPUT = 0.15
W_PERFORMANCE = 0.10
W_LANDING = 0.10
W_COMPLIANCE = 0.05


class ModelCatalogUnavailableError(RuntimeError):
    """Raised when the explicitly selected model catalog has no candidates."""

    def __init__(self, source: str):
        self.source = source
        super().__init__(f"Model catalog '{source}' is unavailable or empty")


class ModelRecommendationService:
    """
    Rule-based model recommendation service.
    No LLM or vector DB required.
    """

    def __init__(self):
        self.model_repository = get_model_asset_repository()
        self.models = self.model_repository.list_models()
        self.tags_data = load_tags()
        self.data_fields = load_data_fields()
        self.synonym_map = build_synonym_map(self.tags_data)
        self.llm = get_llm_client()
        self.explainer = ExplanationGenerator(self.llm)
        self.data_readiness = DataReadinessService()
        self.rec_weights = self._load_recommendation_weights()
        self.rerank_config = self._load_rerank_config()
        self.score_blend = self._load_score_blend()
        self.hybrid_config = self._load_hybrid_config()
        self.keyword_rules = self._load_keyword_rules()
        self.graph = get_knowledge_graph_service()
        self.hybrid_retriever = HybridModelRetriever(
            full_text_weight=self.hybrid_config["full_text_weight"],
            title_text_weight=self.hybrid_config["title_text_weight"],
            dense_enabled=self.hybrid_config["dense_enabled"],
            dense_weight=self.hybrid_config["dense_weight"],
            dense_model=self.hybrid_config["dense_model"],
            dense_cache_enabled=self.hybrid_config["dense_cache_enabled"],
            dense_cache_dir=self.hybrid_config["dense_cache_dir"],
            runtime_mode=self.hybrid_config["runtime_mode"],
            dense_required=self.hybrid_config["dense_required"],
            dense_offline=self.hybrid_config["dense_offline"],
            dense_expected_dimension=self.hybrid_config["dense_expected_dimension"],
            dense_expected_revision=self.hybrid_config["dense_expected_revision"],
            dense_manifest_path=self.hybrid_config["dense_manifest_path"],
            dense_verify_manifest=self.hybrid_config["dense_verify_manifest"],
            dense_config_error=self.hybrid_config["dense_config_error"],
        )
        self._llm_rerank_cache: dict[str, dict[str, list[str]]] = {}
        self.last_hybrid_retrieval_audit: dict[str, Any] = {}
        self.last_llm_rerank_audit: dict[str, Any] = {}
        self._recommend_cache_ttl_seconds = max(
            0.0, float(os.getenv("RECOMMEND_CACHE_TTL_SECONDS", "2"))
        )
        self._recommend_cache: dict[str, tuple[float, RecommendModelsResponse]] = {}
        self._recommend_key_locks: dict[str, threading.Lock] = {}
        self._recommend_cache_guard = threading.Lock()

    @staticmethod
    def _project_root() -> Path:
        """Resolve project root directory."""
        return Path(__file__).resolve().parent.parent.parent.parent

    def dense_runtime_status(self) -> dict[str, Any]:
        """Expose the retriever's actual dense readiness without loading it again."""
        return self.hybrid_retriever.runtime_status()

    def warmup_dense_runtime(self) -> dict[str, Any]:
        """Build the official dense index once so readiness is known at startup."""
        official_models = [model for model in self.models if model.get("source") == "official"]
        return self.hybrid_retriever.warmup(official_models)

    def _recommendation_weights_path(self) -> Path:
        """Return the path to the recommendation weights config file.

        Override this in tests to point to a temporary config.
        """
        return self._project_root() / "data" / "config" / "recommendation_weights.json"

    def _keyword_rules_path(self) -> Path:
        """Return the path to the externalized keyword rules config file."""
        return self._project_root() / "data" / "config" / "keyword_rules.json"

    def _load_keyword_rules(self) -> dict[str, Any]:
        """Load externalized keyword alignment rules from config.

        Falls back to an empty rule set (no adjustments) if the file is missing
        or malformed, so the pipeline degrades gracefully rather than crashing.
        Each rule carries an ``applies_to`` field ("demo" = official-eval mode
        excluded; "all" = always active) so the same config serves both modes.
        """
        config_path = self._keyword_rules_path()
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                rules = json.load(f)
            logger.info("Loaded keyword rules from %s", config_path)
            return rules
        except Exception as exc:
            logger.warning(
                "Failed to load keyword rules from %s: %s, using empty rules",
                config_path,
                exc,
            )
            return {
                "targeted_rules": [],
                "pair_rules": [],
                "groups": [],
                "cross_domain_penalty": None,
                "clamp": {"min": -24.0, "max": 36.0},
            }

    def _load_rerank_config(self) -> dict[str, Any]:
        """Load LLM constrained-rerank parameters from the weights config.

        Reads the ``rerank`` block of ``recommendation_weights.json``. Falls back
        to conservative defaults when the block is
        absent so existing behavior is preserved for installs that predate it.
        """
        config_path = self._recommendation_weights_path()
        defaults = {
            "candidate_pool": 30,
            "llm_weight": 0.35,
            "repair_attempts": 1,
            "cache_enabled": True,
            "required_ranked_count": 10,
        }
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            block = config.get("rerank", {})
            loaded = {
                "candidate_pool": int(block.get("candidate_pool", defaults["candidate_pool"])),
                "llm_weight": float(block.get("llm_weight", defaults["llm_weight"])),
                "repair_attempts": int(block.get("repair_attempts", defaults["repair_attempts"])),
                "cache_enabled": bool(block.get("cache_enabled", defaults["cache_enabled"])),
                "required_ranked_count": int(block.get("required_ranked_count", defaults["required_ranked_count"])),
            }
            if loaded["candidate_pool"] < 5:
                raise ValueError("rerank candidate_pool must be at least 5")
            if not 0 <= loaded["llm_weight"] <= 1:
                raise ValueError("rerank llm_weight must be between 0 and 1")
            if loaded["repair_attempts"] < 0:
                raise ValueError("rerank repair_attempts cannot be negative")
            if not 5 <= loaded["required_ranked_count"] <= loaded["candidate_pool"]:
                raise ValueError("required_ranked_count must be between 5 and candidate_pool")
            return loaded
        except Exception:
            return defaults

    def _load_score_blend(self) -> dict[str, float]:
        """Load the base/graph/field score blend coefficients from config.

        ``total = base_total*base + graph_path_match*graph + field_compat*field``.
        Falls back to legacy defaults (0.93/0.04/0.03) when missing.
        """
        config_path = self._recommendation_weights_path()
        defaults = {"base": 0.93, "graph": 0.04, "field": 0.03}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            block = config.get("score_blend", {})
            return {
                "base": float(block.get("base", defaults["base"])),
                "graph": float(block.get("graph", defaults["graph"])),
                "field": float(block.get("field", defaults["field"])),
            }
        except Exception:
            return defaults

    def _load_hybrid_config(self) -> dict[str, Any]:
        """Load hybrid sparse/dense retrieval and fusion parameters."""
        defaults: dict[str, Any] = {
            "enabled": True,
            "rule_weight": 0.10,
            "retrieval_weight": 0.90,
            "full_text_weight": 0.72,
            "title_text_weight": 0.28,
            "candidate_pool": 30,
            "dense_enabled": False,
            "dense_weight": 0.0,
            "dense_model": "BAAI/bge-m3",
            "dense_cache_enabled": True,
            "dense_cache_dir": str(self._project_root() / "data" / "cache" / "embeddings"),
            "runtime_mode": "light",
            "dense_required": False,
            "dense_offline": False,
            "dense_expected_dimension": 1024,
            "dense_expected_revision": "",
            "dense_manifest_path": "",
            "dense_verify_manifest": False,
            "dense_config_error": "",
        }
        try:
            with open(self._recommendation_weights_path(), "r", encoding="utf-8") as f:
                config = json.load(f)
            block = config.get("hybrid_retrieval", {})
            loaded = {
                "enabled": bool(block.get("enabled", defaults["enabled"])),
                "rule_weight": float(block.get("rule_weight", defaults["rule_weight"])),
                "retrieval_weight": float(block.get("retrieval_weight", defaults["retrieval_weight"])),
                "full_text_weight": float(block.get("full_text_weight", defaults["full_text_weight"])),
                "title_text_weight": float(block.get("title_text_weight", defaults["title_text_weight"])),
                "candidate_pool": int(block.get("candidate_pool", defaults["candidate_pool"])),
                "dense_enabled": bool(block.get("dense_enabled", defaults["dense_enabled"])),
                "dense_weight": float(block.get("dense_weight", defaults["dense_weight"])),
                "dense_model": str(block.get("dense_model", defaults["dense_model"])),
                "dense_cache_enabled": bool(block.get("dense_cache_enabled", defaults["dense_cache_enabled"])),
                "dense_cache_dir": str(block.get("dense_cache_dir", defaults["dense_cache_dir"])),
                "runtime_mode": str(block.get("runtime_mode", defaults["runtime_mode"])),
                "dense_required": bool(block.get("dense_required", defaults["dense_required"])),
                "dense_offline": bool(block.get("dense_offline", defaults["dense_offline"])),
                "dense_expected_dimension": int(
                    block.get("dense_expected_dimension", defaults["dense_expected_dimension"])
                ),
                "dense_expected_revision": str(
                    block.get("dense_expected_revision", defaults["dense_expected_revision"])
                ),
                "dense_manifest_path": str(
                    block.get("dense_manifest_path", defaults["dense_manifest_path"])
                ),
                "dense_verify_manifest": bool(
                    block.get("dense_verify_manifest", defaults["dense_verify_manifest"])
                ),
                "dense_config_error": "",
            }
            runtime_mode_env = os.getenv("RETRIEVAL_RUNTIME_MODE")
            enabled_env = os.getenv("HYBRID_RETRIEVAL_ENABLED")
            dense_enabled_env = os.getenv("HYBRID_DENSE_ENABLED")
            dense_weight_env = os.getenv("HYBRID_DENSE_WEIGHT")
            dense_model_env = os.getenv("HYBRID_DENSE_MODEL")
            dense_cache_enabled_env = os.getenv("HYBRID_DENSE_CACHE_ENABLED")
            dense_cache_dir_env = os.getenv("HYBRID_DENSE_CACHE_DIR")
            dense_required_env = os.getenv("HYBRID_DENSE_REQUIRED")
            dense_offline_env = os.getenv("HYBRID_DENSE_OFFLINE")
            dense_dimension_env = os.getenv("HYBRID_DENSE_EXPECTED_DIMENSION")
            dense_revision_env = os.getenv("HYBRID_DENSE_EXPECTED_REVISION")
            dense_manifest_env = os.getenv("HYBRID_DENSE_MANIFEST")
            dense_verify_manifest_env = os.getenv("HYBRID_DENSE_VERIFY_MANIFEST")
            if runtime_mode_env:
                loaded["runtime_mode"] = runtime_mode_env.strip().lower()
            if enabled_env is not None:
                loaded["enabled"] = enabled_env.lower() == "true"
            if dense_enabled_env is not None:
                loaded["dense_enabled"] = dense_enabled_env.lower() == "true"
            if dense_weight_env is not None:
                loaded["dense_weight"] = float(dense_weight_env)
            if dense_model_env:
                loaded["dense_model"] = dense_model_env.strip()
            if dense_cache_enabled_env is not None:
                loaded["dense_cache_enabled"] = dense_cache_enabled_env.lower() == "true"
            if dense_cache_dir_env:
                loaded["dense_cache_dir"] = dense_cache_dir_env.strip()
            if dense_required_env is not None:
                loaded["dense_required"] = dense_required_env.lower() == "true"
            if dense_offline_env is not None:
                loaded["dense_offline"] = dense_offline_env.lower() == "true"
            if dense_dimension_env:
                loaded["dense_expected_dimension"] = int(dense_dimension_env)
            if dense_revision_env:
                loaded["dense_expected_revision"] = dense_revision_env.strip().lower()
            if dense_manifest_env:
                loaded["dense_manifest_path"] = dense_manifest_env.strip()
            if dense_verify_manifest_env is not None:
                loaded["dense_verify_manifest"] = dense_verify_manifest_env.lower() == "true"
            if loaded["runtime_mode"] not in {"light", "competition_dense"}:
                raise ValueError("retrieval runtime mode must be light or competition_dense")
            if loaded["runtime_mode"] == "competition_dense":
                loaded["dense_required"] = True
                loaded["dense_offline"] = True
                loaded["dense_verify_manifest"] = True
            if not loaded["dense_cache_dir"].strip():
                raise ValueError("hybrid dense_cache_dir cannot be empty")
            cache_dir = Path(loaded["dense_cache_dir"])
            if not cache_dir.is_absolute():
                cache_dir = self._project_root() / cache_dir
            loaded["dense_cache_dir"] = str(cache_dir.resolve())
            manifest_path = str(loaded["dense_manifest_path"] or "").strip()
            if manifest_path:
                resolved_manifest = Path(manifest_path)
                if not resolved_manifest.is_absolute():
                    resolved_manifest = self._project_root() / resolved_manifest
                loaded["dense_manifest_path"] = str(resolved_manifest.resolve())
            if loaded["dense_expected_dimension"] < 0:
                raise ValueError("dense expected dimension cannot be negative")
            if abs(loaded["rule_weight"] + loaded["retrieval_weight"] - 1.0) > 1e-9:
                raise ValueError("hybrid rule/retrieval weights must sum to 1")
            if abs(loaded["full_text_weight"] + loaded["title_text_weight"] - 1.0) > 1e-9:
                raise ValueError("hybrid full/title weights must sum to 1")
            bounded_weights = (
                loaded["rule_weight"],
                loaded["retrieval_weight"],
                loaded["full_text_weight"],
                loaded["title_text_weight"],
                loaded["dense_weight"],
            )
            if not all(0 <= value <= 1 for value in bounded_weights):
                raise ValueError("hybrid weights must be between 0 and 1")
            if loaded["candidate_pool"] < 5:
                raise ValueError("hybrid candidate_pool must be at least 5")
            return loaded
        except Exception as exc:
            logger.warning("Failed to load hybrid retrieval config (%s); using safe recovery", exc)
            if os.getenv("RETRIEVAL_RUNTIME_MODE", "").strip().lower() == "competition_dense":
                recovered = dict(defaults)
                recovered.update(
                    {
                        "runtime_mode": "competition_dense",
                        "dense_required": True,
                        "dense_offline": True,
                        "dense_verify_manifest": True,
                        "dense_enabled": os.getenv("HYBRID_DENSE_ENABLED", "true").lower() == "true",
                        "dense_model": os.getenv("HYBRID_DENSE_MODEL", defaults["dense_model"]),
                        "dense_expected_revision": os.getenv(
                            "HYBRID_DENSE_EXPECTED_REVISION", ""
                        ).strip().lower(),
                        "dense_manifest_path": os.getenv("HYBRID_DENSE_MANIFEST", ""),
                        "dense_config_error": f"CONFIG_{exc.__class__.__name__.upper()}",
                    }
                )
                try:
                    recovered["dense_weight"] = float(os.getenv("HYBRID_DENSE_WEIGHT", "0.5"))
                except ValueError:
                    recovered["dense_weight"] = 0.0
                return recovered
            return defaults

    def _load_recommendation_weights(self) -> dict[str, float]:
        """Load recommendation weights from config file with fallback to defaults.

        Reads data/config/recommendation_weights.json and maps the business-facing
        weights to the 7 internal scoring dimensions. Falls back to hardcoded
        defaults if the file is missing, malformed, or contains invalid values.
        """
        config_path = self._recommendation_weights_path()
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Map business-facing config keys to internal 7 dimensions
            weights: dict[str, float] = {
                "scenario": float(config.get("scenario_match", 20)),
                "customer": float(config.get("customer_match", 10)),
                "data": float(config.get("intent_match", 30)),
                "output": float(config.get("output_match", 10)),
                "performance": float(config.get("tag_overlap", 25)),
                "landing": float(config.get("deployment_bonus", 5)),
                "compliance": float(config.get("semantic_overlap", 10)) * 0.5,
            }
            total = sum(weights.values())
            if total <= 0:
                raise ValueError(f"Total positive weight is zero or negative: {total}")
            normalized = {k: v / total for k, v in weights.items()}
            logger.info("Loaded recommendation weights from %s", config_path)
            return normalized
        except Exception as exc:
            logger.warning(
                "Failed to load recommendation weights from %s: %s, using defaults",
                config_path,
                exc,
            )
            return {
                "scenario": W_SCENARIO,
                "customer": W_CUSTOMER,
                "data": W_DATA,
                "output": W_OUTPUT,
                "performance": W_PERFORMANCE,
                "landing": W_LANDING,
                "compliance": W_COMPLIANCE,
            }

    def _normalize_tag_to_key(self, tag: str) -> str:
        """Normalize a tag value to a standard key for comparison."""
        if not tag:
            return ""
        tag = str(tag).strip()
        if tag in self.synonym_map:
            return self.synonym_map[tag]
        return tag

    def _tokenize_text(self, text: str) -> set[str]:
        """Tokenize text for semantic overlap scoring."""
        text = str(text or "").lower()
        for ch in [",", "，", "。", "、", ";", "；", "/", "|", "(", ")", "（", "）", "[", "]", "\n", "\t", "：", ":"]:
            text = text.replace(ch, " ")

        tokens: set[str] = set()
        for part in text.split():
            if part:
                tokens.add(part)
                for sub in part.split("_"):
                    if sub:
                        tokens.add(sub)
                for sub in re.findall(r"[a-z]+|\d+|[a-z]*\d+[a-z\d-]*", part):
                    if len(sub) >= 2:
                        tokens.add(sub)

        # Chinese text often has no spaces. Character n-grams make official model
        # names such as “阳光E贷” and “贷记卡账单分期” match naturally.
        for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            max_n = min(6, len(run))
            for n in range(2, max_n + 1):
                for i in range(0, len(run) - n + 1):
                    tokens.add(run[i:i + n])

        keywords = [
            "反洗钱", "可疑交易", "大额交易", "合规", "监管", "报表",
            "网点", "客流", "排班", "资源", "调配", "绩效", "流程", "时效",
            "流失", "挽留", "沉睡", "唤醒", "首贷", "白名单", "转化",
            "小微", "农户", "对公", "企业", "信用卡", "逾期", "违约",
            "欺诈", "反欺诈", "准入", "额度", "授信", "预警", "异常",
            "阳光e贷", "aum", "etc", "手机银行", "贷记卡", "分期", "收单",
            "增存", "流失预警", "准入评分", "评分卡", "贷款中介", "潜客",
        ]
        for kw in keywords:
            if kw in text:
                tokens.add(kw)

        return tokens

    def _token_overlap_score(self, query_text: str, model_text: str) -> float:
        """Compute token overlap ratio for semantic matching."""
        q = self._tokenize_text(query_text)
        m = self._tokenize_text(model_text)
        if not q or not m:
            return 0.0
        return len(q & m) / max(len(q), 1)

    def _token_similarity_score(self, query_text: str, model_text: str) -> float:
        """Compute a symmetric semantic score in the 0-100 range."""
        q = self._tokenize_text(query_text)
        m = self._tokenize_text(model_text)
        if not q or not m:
            return 0.0
        intersection = len(q & m)
        jaccard = intersection / max(len(q | m), 1)
        containment = intersection / max(min(len(q), len(m)), 1)
        return min(100.0, max(jaccard, containment) * 100)

    def _query_text(self, parse_result: dict[str, Any]) -> str:
        """Build a rich query text from parse output for matching."""
        return " ".join([
            str(parse_result.get("raw_text", "")),
            str(parse_result.get("normalized_query", "")),
            str(parse_result.get("business_scenario", "")),
            " ".join(map(str, parse_result.get("tags", []))),
            " ".join(map(str, parse_result.get("tag_names", []))),
            " ".join(map(str, parse_result.get("customer_segment", []))),
            " ".join(map(str, parse_result.get("expected_outputs", []))),
            " ".join(map(str, parse_result.get("product_type", []))),
            " ".join(map(str, parse_result.get("risk_type", []))),
        ])

    def _model_text(self, model: dict[str, Any]) -> str:
        """Build a searchable text blob from model metadata."""
        return " ".join([
            str(model.get("model_name", "")),
            str(model.get("canonical_name", "")),
            str(model.get("description", "")),
            str(model.get("search_text", "")),
            " ".join(map(str, model.get("aliases", []))),
            " ".join(map(str, model.get("business_scenario", []))),
            " ".join(map(str, model.get("tags", []))),
            " ".join(map(str, model.get("model_capability", []))),
            " ".join(map(str, model.get("output_fields", []))),
            str(model.get("applicable_conditions", "")),
        ])

    def _semantic_boost(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        """Return a bounded semantic relevance boost for ranking."""
        semantic = self._token_similarity_score(self._query_text(parse_result), self._model_text(model))
        name_boost = self._name_overlap_boost(model, parse_result)
        keyword_adjustment = self._keyword_alignment_adjustment(model, parse_result)
        if model.get("source") == "official":
            return max(-18.0, min(56.0, semantic * 0.55 + name_boost + keyword_adjustment))
        return min(20.0, semantic * 0.30)

    def _adoption_boost(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        """Small bounded boost for models repeatedly adopted in the same role/scenario."""
        role = str(parse_result.get("user_role") or parse_result.get("role") or "")
        scenario = str(
            parse_result.get("business_scenario")
            or parse_result.get("scenario")
            or parse_result.get("intent")
            or ""
        )
        model_id = str(model.get("model_id") or "")
        if not role or not scenario or not model_id:
            return 0.0
        prefetched = parse_result.get("__adoption_rates")
        if isinstance(prefetched, dict):
            stats = prefetched.get(model_id, {})
        else:
            try:
                from app.services.feedback_service import get_feedback_service

                stats = get_feedback_service().model_adoption_rate(
                    model_id=model_id,
                    role=role,
                    scenario=scenario,
                    min_recommendations=5,
                )
            except Exception:
                return 0.0
        if not stats.get("boost_eligible"):
            return 0.0
        return round(min(5.0, float(stats.get("adoption_rate", 0.0)) * 5.0), 2)

    def _name_overlap_boost(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        """Boost distinctive model-name/entity overlaps found in the raw query."""
        query = str(parse_result.get("raw_text") or parse_result.get("normalized_query") or "")
        name = str(model.get("model_name") or model.get("canonical_name") or "")
        if not query or not name:
            return 0.0

        def compact(text: str) -> str:
            return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", text.lower())

        q = compact(query)
        n = compact(name)
        generic = {
            "模型", "客户", "贷款", "评分", "评分卡", "贷前", "贷后", "准入",
            "风险", "营销", "预测", "推荐", "识别", "分析", "机器学习",
            "信用", "个人", "企业", "小微", "银行", "用户",
        }

        best = 0
        max_len = min(12, len(n))
        for size in range(max_len, 2, -1):
            for i in range(0, len(n) - size + 1):
                sub = n[i:i + size]
                if sub in generic or sub.isdigit():
                    continue
                if sub in q:
                    best = max(best, size)
            if best:
                break

        if best >= 8:
            return 28.0
        if best >= 5:
            return 20.0
        if best >= 3:
            return 12.0
        return 0.0

    def _keyword_alignment_adjustment(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        """Reward distinctive business keywords and penalize clear product mismatches.

        Rules are loaded from ``data/config/keyword_rules.json`` (externalized so
        they can be toggled per eval mode and audited independently). Each rule
        carries an ``applies_to`` field: ``"demo"`` rules are skipped in official
        eval mode, ``"all"`` rules always apply.
        """
        # Ablation switch: when disabled, the keyword rules are fully bypassed
        # so callers can measure their isolated contribution to the headline
        # accuracy (see docs/eval/ablation_analysis.md).
        if parse_result.get("__kw_active") is False:
            return 0.0
        query = str(parse_result.get("raw_text") or parse_result.get("normalized_query") or "").lower()
        model_text = self._model_text(model).lower()
        if not query or not model_text:
            return 0.0

        rules = self.keyword_rules
        official_eval_mode = parse_result.get("model_source") == "official"

        def any_in(text: str, keywords: list[str]) -> bool:
            return any(k in text for k in keywords)

        def rule_active(rule: dict[str, Any]) -> bool:
            applies_to = rule.get("applies_to", "all")
            if applies_to == "all":
                return True
            # "demo" rules are skipped in official eval mode.
            return not official_eval_mode

        adjustment = 0.0

        # 1. Targeted rules (multi-condition, demo-only high-precision boosts).
        for rule in rules.get("targeted_rules", []):
            if not rule_active(rule):
                continue
            if (
                any_in(query, rule.get("query_group_a", []))
                and any_in(query, rule.get("query_group_b", []))
                and any_in(model_text, rule.get("model_group", []))
            ):
                adjustment += float(rule.get("reward", 0.0))

        # 2. Pair rules (two query keyword groups + one model keyword group).
        for rule in rules.get("pair_rules", []):
            if not rule_active(rule):
                continue
            if (
                any_in(query, rule.get("query_group_a", []))
                and any_in(query, rule.get("query_group_b", []))
                and any_in(model_text, rule.get("model_group", []))
            ):
                adjustment += float(rule.get("reward", 0.0))

        # 3. Groups (reward when both query and model mention the keyword set,
        #    penalize when only the query mentions it).
        for group in rules.get("groups", []):
            keywords = group.get("keywords", [])
            if not any_in(query, keywords):
                continue
            if any_in(model_text, keywords):
                adjustment += float(group.get("reward", 0.0))
            else:
                adjustment += float(group.get("penalty", 0.0))

        # 4. Cross-domain penalty (e.g. recommending a marketing model for a
        #    credit-risk demand).
        cdp = rules.get("cross_domain_penalty")
        if cdp and rule_active(cdp):
            if (
                str(parse_result.get("intent") or "") == cdp.get("intent")
                and str(model.get("domain") or "") == cdp.get("model_domain")
                and any_in(query, cdp.get("query_keywords", []))
            ):
                adjustment += float(cdp.get("penalty", 0.0))

        clamp = rules.get("clamp", {"min": -24.0, "max": 36.0})
        return max(float(clamp.get("min", -24.0)), min(float(clamp.get("max", 36.0)), adjustment))

    def _model_pool(self, parse_result: dict[str, Any]) -> list[dict[str, Any]]:
        """Return one explicitly selected catalog; never mix or silently fall back."""
        source = str(
            parse_result.get("model_source")
            or parse_result.get("catalog_source")
            or "official"
        ).lower()
        if source not in {"official", "demo"}:
            raise ValueError(f"Unsupported model catalog source: {source}")
        filtered = [m for m in self.models if m.get("source") == source]
        if not filtered:
            raise ModelCatalogUnavailableError(source)
        return filtered

    def recommend(
        self,
        parse_result: dict[str, Any],
        top_k: int = 5,
        demo_top_k: int = 3,
        prefer_api_available: bool = False,
        prefer_landing_cases: bool = False,
        use_llm: bool | None = None,
        use_llm_reason: bool | None = None,
        use_keyword_rules: bool | None = None,
        use_hybrid_retrieval: bool | None = None,
    ) -> RecommendModelsResponse:
        """Deduplicate short bursts of identical deterministic ranking work."""
        cache_payload = {
            "parse_result": {
                key: value for key, value in parse_result.items()
                if not key.startswith("__") and key != "session_id"
            },
            "top_k": top_k,
            "demo_top_k": demo_top_k,
            "prefer_api_available": prefer_api_available,
            "prefer_landing_cases": prefer_landing_cases,
            "use_llm": use_llm,
            "use_llm_reason": use_llm_reason,
            "use_keyword_rules": use_keyword_rules,
            "use_hybrid_retrieval": use_hybrid_retrieval,
            "weights": self.rec_weights,
            "rerank": self.rerank_config,
            "hybrid": self.hybrid_config,
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        with self._recommend_cache_guard:
            key_lock = self._recommend_key_locks.setdefault(cache_key, threading.Lock())
        with key_lock:
            now = time.monotonic()
            cached = self._recommend_cache.get(cache_key)
            if self._recommend_cache_ttl_seconds > 0 and cached and cached[0] >= now:
                cloned = RecommendModelsResponse.model_validate(cached[1].model_dump())
                cloned.request_id = f"rec-{uuid.uuid4().hex[:8]}"
                return cloned
            result = self._recommend_uncached(
                parse_result=parse_result,
                top_k=top_k,
                demo_top_k=demo_top_k,
                prefer_api_available=prefer_api_available,
                prefer_landing_cases=prefer_landing_cases,
                use_llm=use_llm,
                use_llm_reason=use_llm_reason,
                use_keyword_rules=use_keyword_rules,
                use_hybrid_retrieval=use_hybrid_retrieval,
            )
            if self._recommend_cache_ttl_seconds > 0:
                self._recommend_cache[cache_key] = (
                    time.monotonic() + self._recommend_cache_ttl_seconds,
                    RecommendModelsResponse.model_validate(result.model_dump()),
                )
                if len(self._recommend_cache) > 128:
                    self._recommend_cache = {
                        key: value for key, value in self._recommend_cache.items()
                        if value[0] >= time.monotonic()
                    }
            return result

    def _recommend_uncached(
        self,
        parse_result: dict[str, Any],
        top_k: int = 5,
        demo_top_k: int = 3,
        prefer_api_available: bool = False,
        prefer_landing_cases: bool = False,
        use_llm: bool | None = None,
        use_llm_reason: bool | None = None,
        use_keyword_rules: bool | None = None,
        use_hybrid_retrieval: bool | None = None,
    ) -> RecommendModelsResponse:
        """Run full recommendation pipeline.

        Ablation switches (used by ablation eval, default behavior unchanged):
        - use_llm: force-enable/disable every LLM path (rerank + reason).
            ``None`` keeps legacy behavior (LLM on when ``self.llm.available``).
        - use_llm_reason: independently disable explanation polishing while
            keeping constrained LLM reranking active during evaluation.
        - use_keyword_rules: force-enable/disable the hardcoded keyword
            alignment rules (pair_rules + groups). ``None`` = legacy (on).
        - use_hybrid_retrieval: enable the factual knowledge-card retrieval
            layer. ``None`` follows the checked-in configuration.
        """
        source = str(
            parse_result.get("model_source")
            or parse_result.get("catalog_source")
            or "official"
        ).lower()
        if source == "official_then_demo":
            official_parse = dict(parse_result)
            official_parse["model_source"] = "official"
            official_result = self._recommend_uncached(
                parse_result=official_parse,
                top_k=top_k,
                demo_top_k=0,
                prefer_api_available=prefer_api_available,
                prefer_landing_cases=prefer_landing_cases,
                use_llm=use_llm,
                use_llm_reason=use_llm_reason,
                use_keyword_rules=use_keyword_rules,
                use_hybrid_retrieval=use_hybrid_retrieval,
            )

            demo_references: list[RecommendedModel] = []
            demo_status = "not_requested" if demo_top_k == 0 else "unavailable"
            if demo_top_k > 0:
                demo_parse = dict(parse_result)
                demo_parse["model_source"] = "demo"
                try:
                    demo_result = self._recommend_uncached(
                        parse_result=demo_parse,
                        top_k=demo_top_k,
                        demo_top_k=0,
                        prefer_api_available=prefer_api_available,
                        prefer_landing_cases=prefer_landing_cases,
                        # Demo references are supplementary and must not double
                        # the external LLM calls made for the official ranking.
                        use_llm=False,
                        use_llm_reason=False,
                        use_keyword_rules=use_keyword_rules,
                        use_hybrid_retrieval=use_hybrid_retrieval,
                    )
                    demo_references = demo_result.recommendations
                    for rank, item in enumerate(demo_references, start=1):
                        item.rank = rank
                    demo_status = "available"
                except ModelCatalogUnavailableError:
                    logger.warning(
                        "Demo reference catalog is unavailable; returning official ranking only"
                    )

            summary = official_result.summary
            if demo_status == "available":
                summary = (
                    f"{summary} 另提供{len(demo_references)}个脱敏Demo参考候选；"
                    "Demo不属于官方榜单，不计入官方评估或组合推荐。"
                ).strip()
            elif demo_status == "unavailable":
                summary = (
                    f"{summary} Demo参考目录当前不可用；官方榜单未回退、未受影响。"
                ).strip()

            return RecommendModelsResponse(
                request_id=f"rec-{uuid.uuid4().hex[:8]}",
                recommendations=official_result.recommendations,
                demo_references=demo_references,
                unrecommended_examples=official_result.unrecommended_examples,
                summary=summary,
                catalog_policy="official_then_demo",
                demo_reference_status=demo_status,
                official_recommendation_count=len(official_result.recommendations),
                demo_reference_count=len(demo_references),
            )
        if source not in {"official", "demo"}:
            raise ValueError(f"Unsupported model catalog source: {source}")

        # Resolve ablation switches into concrete booleans, then thread them
        # through the pipeline so callers can reproduce a pure-rule baseline.
        llm_active = self.llm.available if use_llm is None else (use_llm and self.llm.available)
        llm_reason_active = (
            llm_active
            if use_llm_reason is None
            else bool(use_llm_reason and self.llm.available)
        )
        kw_active = True if use_keyword_rules is None else bool(use_keyword_rules)
        hybrid_active = (
            bool(self.hybrid_config.get("enabled", True))
            if use_hybrid_retrieval is None
            else bool(use_hybrid_retrieval)
        )
        # Stash on parse_result so downstream helpers (_semantic_boost /
        # _generate_reason) observe the same switch without new plumbing.
        parse_result = dict(parse_result)
        parse_result["__llm_active"] = llm_reason_active
        parse_result["__kw_active"] = kw_active
        parse_result["__hybrid_active"] = hybrid_active
        role = str(parse_result.get("user_role") or parse_result.get("role") or "")
        scenario = str(
            parse_result.get("business_scenario")
            or parse_result.get("scenario")
            or parse_result.get("intent")
            or ""
        )
        try:
            from app.services.feedback_service import get_feedback_service

            parse_result["__adoption_rates"] = get_feedback_service().adoption_rates(
                role=role,
                scenario=scenario,
                min_recommendations=5,
            )
        except Exception:
            parse_result["__adoption_rates"] = {}

        model_pool = self._model_pool(parse_result)

        # 1. Recall candidate models
        retrieval_scores: dict[str, HybridRetrievalScore] = {}
        if hybrid_active:
            # The catalog is small (currently 165 assets), so score the full
            # selected source and let retrieval/reranking decide. This avoids
            # losing semantically relevant models through a brittle pre-filter.
            candidates = model_pool[:]
            retrieval_scores = self.hybrid_retriever.score(
                self._query_text(parse_result), candidates
            )
            self.last_hybrid_retrieval_audit = {
                **self.hybrid_retriever.last_audit,
                "rule_weight": self.hybrid_config["rule_weight"],
                "retrieval_weight": self.hybrid_config["retrieval_weight"],
                "candidate_pool": self.hybrid_config["candidate_pool"],
            }
        else:
            candidates = self._recall(parse_result, model_pool)
            self.last_hybrid_retrieval_audit = {
                "enabled": False,
                "candidate_count": len(candidates),
                "mode": "disabled",
            }

        if not candidates:
            # Fallback: return all models with low scores
            candidates = model_pool[:]

        # 2. Score candidates
        scored = []
        for model in candidates:
            score, breakdown = self._score(model, parse_result)
            score = round(min(100.0, score + self._semantic_boost(model, parse_result) + self._adoption_boost(model, parse_result)), 1)
            scored.append((model, score, breakdown))

        if hybrid_active and scored:
            scored = self._fuse_hybrid_scores(scored, retrieval_scores)

        # 3. Sort by score descending
        scored.sort(key=lambda x: (-x[1], x[0].get("model_id", "")))

        # 3.5 LLM Semantic Reranking (when available and not disabled by ablation)
        if llm_active and len(scored) > top_k:
            llm_ranks = self._semantic_rerank_with_llm(scored, parse_result)
            if llm_ranks:
                scored = llm_ranks

        # 4. Apply preference boosters
        if prefer_api_available:
            scored.sort(key=lambda x: (0 if x[0].get("api_available") else 1, -x[1]))
        if prefer_landing_cases:
            scored.sort(key=lambda x: (
                -(len(x[0].get("historical_cases", [])) if x[0].get("historical_cases") else 0),
                -x[1]
            ))

        # 5. Build response
        top = scored[:top_k]
        recommendations = []
        for rank, (model, score, breakdown) in enumerate(top, 1):
            rec = self._build_recommended(model, parse_result, score, breakdown, rank)
            recommendations.append(rec)

        # 6. Unrecommended examples
        unrecommended = self._find_unrecommended(scored, top_k, parse_result)

        # 7. Summary
        summary = self._generate_summary(parse_result, recommendations)

        return RecommendModelsResponse(
            request_id=f"rec-{uuid.uuid4().hex[:8]}",
            recommendations=recommendations,
            unrecommended_examples=unrecommended,
            summary=summary,
            catalog_policy=source,
            demo_reference_status="not_requested",
            official_recommendation_count=(
                len(recommendations) if source == "official" else 0
            ),
            demo_reference_count=0,
        )

    def _fuse_hybrid_scores(
        self,
        scored: list[tuple[dict[str, Any], float, ScoreBreakdown]],
        retrieval_scores: dict[str, HybridRetrievalScore],
    ) -> list[tuple[dict[str, Any], float, ScoreBreakdown]]:
        """Fuse normalized structured scores with auditable retrieval scores."""
        raw_scores = [item[1] for item in scored]
        low = min(raw_scores)
        high = max(raw_scores)
        span = max(high - low, 1e-9)
        rule_weight = float(self.hybrid_config.get("rule_weight", 0.10))
        retrieval_weight = float(self.hybrid_config.get("retrieval_weight", 0.90))
        fused: list[tuple[dict[str, Any], float, ScoreBreakdown]] = []
        for model, raw_score, breakdown in scored:
            model_id = str(model.get("model_id") or "")
            retrieval = retrieval_scores.get(model_id, HybridRetrievalScore())
            normalized_rule = (raw_score - low) / span
            fused_score = 100.0 * (
                normalized_rule * rule_weight
                + retrieval.retrieval_score * retrieval_weight
            )
            payload = breakdown.model_dump()
            payload["hybrid_retrieval_match"] = round(retrieval.retrieval_score * 100.0, 1)
            fused.append((model, round(min(100.0, fused_score), 1), ScoreBreakdown(**payload)))
        return fused

    def _recall(self, parse_result: dict[str, Any], model_pool: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Recall candidate models by domain, scenario, tags, and semantic overlap."""
        model_pool = model_pool or self.models
        intent = parse_result.get("intent", "")
        tags = parse_result.get("tags", [])
        scenario = parse_result.get("business_scenario", "")
        customers = parse_result.get("customer_segment", [])
        outputs = parse_result.get("expected_outputs", [])

        # Build query text for semantic overlap
        query_text = self._query_text(parse_result)

        candidates = []
        seen_ids: set[str] = set()

        for m in model_pool:
            score = 0.0
            reasons = 0

            # Domain match
            if intent and m.get("domain") == intent:
                score += 3
                reasons += 1

            # Scenario match
            if scenario:
                scenario_match = any(s in scenario or scenario in s
                                     for s in m.get("business_scenario", []))
                if scenario_match:
                    score += 3
                    reasons += 1

            # Tag overlap (normalized)
            model_tags = set(
                self._normalize_tag_to_key(t).lower()
                for t in m.get("tags", [])
            )
            query_tags = set(
                self._normalize_tag_to_key(t).lower()
                for t in tags
            )
            if query_tags and model_tags:
                overlap = len(query_tags & model_tags)
                if overlap > 0:
                    score += overlap * 1.5
                    reasons += 1

            # Customer segment match
            if customers:
                for c in customers:
                    c_lower = c.lower()
                    if any(c_lower in seg.lower() for seg in m.get("customer_segment", [])):
                        score += 2
                        reasons += 1
                        break

            # Output match
            if outputs:
                m_outputs_set = set(o.lower() for o in m.get("output_fields", []))
                query_outputs = set(o.lower() for o in outputs)
                if query_outputs & m_outputs_set:
                    score += 2
                    reasons += 1

            # Capability match from tags (normalized)
            tag_caps = set(
                self._normalize_tag_to_key(t).lower()
                for t in tags
            )
            model_cap = set(
                self._normalize_tag_to_key(c).lower()
                for c in m.get("model_capability", [])
            )
            if tag_caps & model_cap:
                score += 2.5
                reasons += 1

            # Semantic overlap from full text
            semantic_score = self._token_similarity_score(query_text, self._model_text(m))
            if semantic_score > 5:
                score += semantic_score * 4
                reasons += 1

            if reasons >= 1 and m["model_id"] not in seen_ids:
                candidates.append(m)
                seen_ids.add(m["model_id"])

        # If too few candidates, relax recall
        if len(candidates) < 5:
            for m in model_pool:
                if m["model_id"] not in seen_ids:
                    candidates.append(m)
                    seen_ids.add(m["model_id"])

        return candidates

    def _score(self, model: dict[str, Any], parse_result: dict[str, Any]) -> tuple[float, ScoreBreakdown]:
        """Compute multi-dimensional score."""
        scenario = parse_result.get("business_scenario", "")
        customers = parse_result.get("customer_segment", [])
        tags = parse_result.get("tags", [])
        outputs = parse_result.get("expected_outputs", [])
        data_conds = parse_result.get("data_conditions", [])

        scenario_s = self._calc_scenario_match(model, scenario)
        customer_s = self._calc_customer_match(model, customers)
        data_s = self._calc_data_match(model, data_conds)
        output_s = self._calc_output_match(model, outputs, tags)
        graph_s = self._calc_graph_path_match(model, parse_result)
        field_compat_s = self._calc_field_compatibility(model, parse_result)
        perf_s = self._calc_performance(model)
        landing_s = self._calc_landing(model)
        compliance_s = self._calc_compliance(model)

        w = self.rec_weights
        base_total = (
            scenario_s * w.get("scenario", W_SCENARIO) +
            customer_s * w.get("customer", W_CUSTOMER) +
            data_s * w.get("data", W_DATA) +
            output_s * w.get("output", W_OUTPUT) +
            perf_s * w.get("performance", W_PERFORMANCE) +
            landing_s * w.get("landing", W_LANDING) +
            compliance_s * w.get("compliance", W_COMPLIANCE)
        )
        total = (
            base_total * self.score_blend.get("base", 0.93)
            + graph_s * self.score_blend.get("graph", 0.04)
            + field_compat_s * self.score_blend.get("field", 0.03)
        )

        breakdown = ScoreBreakdown(
            scenario_match=round(scenario_s, 1),
            customer_match=round(customer_s, 1),
            data_match=round(data_s, 1),
            output_match=round(output_s, 1),
            graph_path_match=round(graph_s, 1),
            field_compatibility=round(field_compat_s, 1),
            llm_semantic_match=0.0,
            performance=round(perf_s, 1),
            landing_experience=round(landing_s, 1),
            compliance=round(compliance_s, 1),
        )

        return round(total, 1), breakdown

    def _calc_scenario_match(self, model: dict[str, Any], scenario: str) -> float:
        """Scenario match score (0-100)."""
        if not scenario:
            return 50.0
        m_scenarios = model.get("business_scenario", [])
        for ms in m_scenarios:
            if scenario == ms:
                return 95.0
            if scenario in ms or ms in scenario:
                return 85.0
            # Check word overlap
            sw = set(scenario.lower().replace(" ", ""))
            mw = set(ms.lower().replace(" ", ""))
            if len(sw & mw) / max(len(sw | mw), 1) > 0.3:
                return 70.0
        # Check domain-level match
        domain = model.get("domain") or ""
        if domain in scenario or scenario in domain:
            return 60.0
        semantic = self._token_similarity_score(scenario, self._model_text(model))
        if semantic >= 20:
            return min(90.0, 50.0 + semantic)
        return 30.0

    def _calc_customer_match(self, model: dict[str, Any], customers: list[str]) -> float:
        """Customer segment match score (0-100)."""
        if not customers:
            return 50.0
        m_segments = model.get("customer_segment", [])
        best = 0.0
        for c in customers:
            c_lower = c.lower()
            for ms in m_segments:
                ms_lower = ms.lower()
                if c_lower == ms_lower:
                    best = max(best, 95.0)
                elif c_lower in ms_lower or ms_lower in c_lower:
                    best = max(best, 80.0)
        return best if best > 0 else 30.0

    def _calc_data_match(self, model: dict[str, Any], data_conds: list[str]) -> float:
        """Data condition match score (0-100)."""
        req_inputs = set(i.lower() for i in model.get("input_fields_required", []))
        if not req_inputs:
            return 50.0
        if not data_conds:
            return 40.0  # No data info available
        cond_set = set(c.lower() for c in data_conds)
        overlap = len(req_inputs & cond_set)
        if overlap > 0:
            ratio = overlap / len(req_inputs)
            return min(100, 30 + ratio * 70)
        return 20.0  # Data mismatch

    def _calc_output_match(self, model: dict[str, Any], outputs: list[str], tags: list[str]) -> float:
        """Output field match score (0-100)."""
        m_outputs = set(o.lower() for o in model.get("output_fields", []))
        if not m_outputs:
            return 30.0

        # Match against expected outputs
        query_set = set(o.lower() for o in outputs)
        if query_set:
            overlap = len(query_set & m_outputs)
            if overlap > 0:
                return min(100, 40 + (overlap / max(len(query_set), 1)) * 60)

        # Fallback: match against tags (normalized)
        tag_set = set(self._normalize_tag_to_key(t).lower() for t in tags)
        model_tags_set = set(self._normalize_tag_to_key(t).lower() for t in model.get("tags", []))
        model_caps_set = set(self._normalize_tag_to_key(c).lower() for c in model.get("model_capability", []))

        cap_overlap = len(tag_set & model_caps_set)
        tag_overlap_len = len(tag_set & model_tags_set)

        if cap_overlap > 0:
            return min(90.0, 60.0 + cap_overlap * 10)

        if tag_overlap_len > 0:
            return min(85.0, 55.0 + tag_overlap_len * 8)

        # Fallback: match against model output fields
        tag_output_overlap = len(tag_set & m_outputs)
        if tag_output_overlap > 0:
            return 60.0

        return 30.0

    def _calc_graph_path_match(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        """Knowledge-graph evidence score (0-100)."""
        match = self.graph.match_path(
            parse_result=parse_result,
            model_id=str(model.get("model_id", "")),
            max_edges=80,
        )
        if not match.matched_node_ids:
            return 50.0
        direct_edges = [
            edge
            for edge in match.edges
            if edge.source == f"model:{model.get('model_id', '')}"
            and edge.target in set(match.matched_node_ids)
        ]
        if not direct_edges:
            return 35.0
        covered_targets = {edge.target for edge in direct_edges}
        coverage = len(covered_targets) / max(len(match.matched_node_ids), 1)
        avg_weight = sum(edge.weight for edge in direct_edges) / len(direct_edges)
        return min(100.0, 45.0 + coverage * 40.0 + avg_weight * 15.0)

    def _calc_field_compatibility(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        """Input/output field compatibility score (0-100)."""
        data_conds = self._as_list(parse_result.get("data_conditions"))
        outputs = self._as_list(parse_result.get("expected_outputs"))
        required_inputs = self._as_list(model.get("input_fields_required"))
        optional_inputs = self._as_list(model.get("input_fields_optional"))
        model_outputs = self._as_list(model.get("output_fields"))

        data_score = 50.0
        if required_inputs:
            if data_conds:
                required_hits = self._soft_overlap_count(required_inputs, data_conds)
                optional_hits = self._soft_overlap_count(optional_inputs, data_conds)
                required_ratio = required_hits / len(required_inputs)
                optional_ratio = optional_hits / max(len(optional_inputs), 1) if optional_inputs else 0.0
                data_score = min(100.0, 25.0 + required_ratio * 60.0 + optional_ratio * 15.0)
            else:
                data_score = 45.0

        output_score = 50.0
        if outputs:
            if model_outputs:
                output_hits = self._soft_overlap_count(model_outputs, outputs)
                output_score = min(100.0, 30.0 + (output_hits / len(outputs)) * 70.0)
            else:
                output_score = 25.0

        if data_conds and outputs:
            return data_score * 0.60 + output_score * 0.40
        if data_conds:
            return data_score
        if outputs:
            return output_score
        return 50.0

    def _calc_performance(self, model: dict[str, Any]) -> float:
        """Model performance score (0-100)."""
        metrics = model.get("performance_metrics", {})
        if not metrics:
            return 50.0

        score = 50.0
        if "auc" in metrics:
            score += metrics["auc"] * 40
        if "ks" in metrics:
            score += metrics["ks"] * 30
        if "recall" in metrics:
            score += metrics["recall"] * 20
        if "precision" in metrics:
            score += metrics["precision"] * 15
        if "lift_top10pct" in metrics:
            score += min(metrics["lift_top10pct"] * 10, 20)
        if "mape" in metrics:
            mape = metrics["mape"]
            if mape > 0:
                score += max(0, (0.3 - mape) * 50)

        return min(100, score)

    def _calc_landing(self, model: dict[str, Any]) -> float:
        """Landing experience score (0-100)."""
        cases = model.get("historical_cases", [])
        if cases:
            n = len(cases)
            return min(100, 50 + n * 10)
        if model.get("deployment_status") == "mock_available":
            return 40.0
        return 30.0

    def _calc_compliance(self, model: dict[str, Any]) -> float:
        """Compliance score (0-100)."""
        boundary = model.get("compliance_boundary", "")
        if not boundary:
            return 50.0
        if "合规" in boundary or "监管" in boundary or "巴塞尔" in boundary:
            return 85.0
        if "个人" in boundary or "数据" in boundary or "隐私" in boundary:
            return 75.0
        return 60.0

    def _build_recommended(
        self,
        model: dict[str, Any],
        parse_result: dict[str, Any],
        total_score: float,
        breakdown: ScoreBreakdown,
        rank: int,
    ) -> RecommendedModel:
        """Build a full RecommendedModel response item."""
        # Evidence cards
        evidence = self._generate_evidence(model, parse_result)

        # Data gap analysis
        required_data = model.get("input_fields_required", []) + model.get("input_fields_optional", [])
        data_readiness = self.data_readiness.diagnose(model, parse_result)
        field_names = {f["field_key"]: f["name"] for f in self.data_fields}
        required_named = [field_names.get(d, d) for d in required_data]
        missing_data = self._analyze_data_gaps(model, parse_result)
        missing_named = [field_names.get(d, d) for d in missing_data]

        # Output fields
        output_named = model.get("output_fields", [])

        # Alternative models
        alternatives = self._find_alternatives(model, parse_result)

        # Reason
        reason = self._generate_reason(model, parse_result, total_score)

        return RecommendedModel(
            model_id=model.get("model_id", ""),
            model_name=model.get("model_name", ""),
            source=model.get("source", ""),
            catalog_version=model.get("catalog_version", ""),
            rank=rank,
            total_score=total_score,
            rule_score=self._rule_score_from_breakdown(breakdown),
            graph_score=self._graph_score_from_breakdown(breakdown),
            retrieval_score=round(breakdown.hybrid_retrieval_match, 1),
            llm_score=round(breakdown.llm_semantic_match, 1),
            score_breakdown=breakdown,
            recommendation_reason=reason,
            evidence_cards=evidence,
            required_data=required_named,
            missing_data=missing_named,
            output_fields=output_named,
            applicable_boundary=model.get("applicable_conditions", ""),
            unsuitable_conditions=model.get("unsuitable_conditions", ""),
            compliance_notes=model.get("compliance_boundary", ""),
            alternative_models=alternatives,
            data_readiness=data_readiness,
        )

    def _generate_evidence(self, model: dict[str, Any], parse_result: dict[str, Any]) -> list[EvidenceCard]:
        """Generate evidence cards for a model."""
        cards: list[EvidenceCard] = []
        provenance = model.get("field_provenance", {})
        case_verified = (
            provenance.get("historical_cases", {}).get("verification") == "source_verified"
        )

        # Never present unverified or synthetic-draft cases as bank evidence.
        cases = model.get("historical_cases", []) if case_verified else []
        for i, case in enumerate(cases[:3]):
            # Handle both string and dict formats
            if isinstance(case, dict):
                content = f"{case.get('client', '')}: {case.get('result', '')}".strip(": ")
            else:
                content = str(case)
            cards.append(EvidenceCard(
                evidence_type="历史案例",
                content=content,
                source=f"模型 {model.get('model_id', '')} 落地案例",
            ))

        # Evidence from business scenario
        scenarios = model.get("business_scenario", [])
        if scenarios:
            cards.append(EvidenceCard(
                evidence_type="业务场景",
                content=f"适用于：{'、'.join(scenarios[:3])}",
                source="模型元数据",
                evidence_text=f"适用于：{'、'.join(scenarios[:3])}",
                source_field="model_metadata.business_scenario",
                confidence=0.85,
            ))

        graph_card = self._generate_graph_evidence_card(model, parse_result)
        if graph_card:
            cards.append(graph_card)

        # If no cards yet, add a generic one
        if not cards:
            cards.append(EvidenceCard(
                evidence_type="基础信息",
                content=f"模型 {model.get('model_name', '')} 已上架模型市场",
                source="模型市场目录",
                evidence_text=f"模型 {model.get('model_name', '')} 已上架模型市场",
                source_field="model_catalog",
                confidence=0.70,
            ))

        return cards[:5]  # Max 5 cards

    def _generate_graph_evidence_card(
        self,
        model: dict[str, Any],
        parse_result: dict[str, Any],
    ) -> EvidenceCard | None:
        """Generate a knowledge-graph evidence card for a recommendation."""
        match = self.graph.match_path(
            parse_result=parse_result,
            model_id=str(model.get("model_id", "")),
            max_edges=20,
        )
        direct_edges = [
            edge
            for edge in match.edges
            if edge.source == f"model:{model.get('model_id', '')}"
            and edge.target in set(match.matched_node_ids)
        ]
        if not direct_edges:
            return None

        node_by_id = {node.node_id: node for node in match.nodes}
        relation_labels = {
            "applies_to": "场景",
            "belongs_to_stage": "阶段",
            "targets_segment": "客群",
            "has_capability": "能力",
            "has_tag": "标签",
            "requires": "输入字段",
            "optional_requires": "可选字段",
            "outputs": "输出字段",
        }
        facts: list[str] = []
        for edge in direct_edges[:6]:
            target = node_by_id.get(edge.target)
            label = relation_labels.get(edge.relation_type, edge.relation_type)
            if target:
                facts.append(f"{label}:{target.name}")
        if not facts:
            return None

        content = "图谱路径命中：" + "；".join(facts)
        confidence = min(0.98, 0.65 + len(direct_edges) * 0.04)
        return EvidenceCard(
            evidence_type="知识图谱路径",
            content=content,
            source="本地知识图谱",
            evidence_text=content,
            source_field="knowledge_graph.direct_edges",
            confidence=round(confidence, 2),
        )

    def _analyze_data_gaps(self, model: dict[str, Any], parse_result: dict[str, Any]) -> list[str]:
        """Identify data gaps between what the model needs and what's available."""
        data_conds = parse_result.get("data_conditions", [])
        cond_set = set(d.lower() for d in data_conds)

        missing: list[str] = []
        for req_field in model.get("input_fields_required", []) + model.get("input_fields_optional", []):
            req_lower = req_field.lower()
            if not any(req_lower in cond or cond in req_lower for cond in cond_set):
                missing.append(req_field)

        return missing

    def _find_alternatives(self, model: dict[str, Any], parse_result: dict[str, Any]) -> list[AlternativeModel]:
        """Find alternative models with similar capabilities."""
        cap = set(model.get("model_capability", []))
        domain = model.get("domain", "")
        model_id = model.get("model_id", "")
        source = model.get("source", "")

        alternatives: list[AlternativeModel] = []
        for m in self.models:
            if m["model_id"] == model_id:
                continue
            if m.get("source", "") != source:
                continue
            m_cap = set(m.get("model_capability", []))
            if cap & m_cap and m.get("domain") == domain:
                alternatives.append(AlternativeModel(
                    model_id=m["model_id"],
                    model_name=m["model_name"],
                    reason=f"相同能力领域：{'、'.join(cap & m_cap)}",
                ))

        return alternatives[:3]

    def _generate_reason(self, model: dict[str, Any], parse_result: dict[str, Any], score: float) -> str:
        """Generate a natural language recommendation reason."""
        parts = []
        tags = parse_result.get("tags", [])
        scenario = parse_result.get("business_scenario", "")

        if scenario:
            parts.append(f"该模型在「{scenario}」场景下")
        else:
            parts.append("该模型")

        # Mention capability
        cap = model.get("model_capability", [])
        if cap:
            parts.append(f"具备{'、'.join(cap[:2])}能力")

        # Mention tag match
        model_tags = set(t.lower() for t in model.get("tags", []))
        query_tags = set(t.lower() for t in tags)
        overlap = model_tags & query_tags
        if overlap:
            parts.append(f"匹配标签：{'、'.join(list(overlap)[:3])}")

        rule_reason = "，".join(parts)
        # Ablation switch: skip the LLM reason entirely in pure-rule mode so the
        # baseline stays a clean rule-only path.
        if parse_result.get("__llm_active") is False:
            return rule_reason
        llm_reason = self.explainer.generate_recommendation_reason(
            model=model,
            parse_result=parse_result,
            fallback_reason=rule_reason,
        )
        return llm_reason["reason"]

    def _rule_score_from_breakdown(self, breakdown: ScoreBreakdown) -> float:
        """Return the base rule score before graph/LLM blending."""
        w = self.rec_weights
        return round(
            breakdown.scenario_match * w.get("scenario", W_SCENARIO)
            + breakdown.customer_match * w.get("customer", W_CUSTOMER)
            + breakdown.data_match * w.get("data", W_DATA)
            + breakdown.output_match * w.get("output", W_OUTPUT)
            + breakdown.performance * w.get("performance", W_PERFORMANCE)
            + breakdown.landing_experience * w.get("landing", W_LANDING)
            + breakdown.compliance * w.get("compliance", W_COMPLIANCE),
            1,
        )

    @staticmethod
    def _graph_score_from_breakdown(breakdown: ScoreBreakdown) -> float:
        """Return raw graph score across path and field compatibility."""
        return round((breakdown.graph_path_match * 0.04 + breakdown.field_compatibility * 0.03) / 0.07, 1)

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple | set):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _soft_overlap_count(left: list[str], right: list[str]) -> int:
        """Count exact or containment overlaps between two field lists."""
        right_norm = [item.lower() for item in right]
        count = 0
        for item in left:
            item_norm = item.lower()
            if any(item_norm == candidate or item_norm in candidate or candidate in item_norm for candidate in right_norm):
                count += 1
        return count

    def _find_unrecommended(
        self,
        scored: list[tuple[dict[str, Any], float, ScoreBreakdown]],
        top_k: int,
        parse_result: dict[str, Any],
    ) -> list[UnrecommendedExample]:
        """Find examples of models that were not recommended."""
        unrecommended: list[UnrecommendedExample] = []
        bottom = scored[top_k:] if len(scored) > top_k else []
        # Take up to 3 from the bottom with lowest scores
        bottom_sorted = sorted(bottom, key=lambda x: x[1])[:3]

        for model, _score, _ in bottom_sorted:
            domain = _domain_display(model.get("domain", ""))
            scenario = parse_result.get("business_scenario", "")
            reason = f"该模型为{domain}模型，与当前场景「{scenario}」的匹配信号较弱"
            unrecommended.append(UnrecommendedExample(
                model_id=model.get("model_id", ""),
                model_name=model.get("model_name", ""),
                reason=reason,
            ))

        return unrecommended

    def _generate_summary(self, parse_result: dict[str, Any], recommendations: list[RecommendedModel]) -> str:
        """Generate a summary of the recommendation results."""
        scenario = parse_result.get("business_scenario", "") or "当前需求"
        n = len(recommendations)
        if n == 0:
            return f"抱歉，未找到匹配「{scenario}」的模型，请调整需求条件后重试。"
        top_name = recommendations[0].model_name
        return (
            f"已为您推荐{n}个匹配「{scenario}」的模型"
            f"，首选「{top_name}」"
            f"，涵盖{'、'.join(r.model_name for r in recommendations[:3])}等能力。"
        )

    def _semantic_rerank_with_llm(
        self,
        scored: list[tuple[dict[str, Any], float, ScoreBreakdown]],
        parse_result: dict[str, Any],
    ) -> list[tuple[dict[str, Any], float, ScoreBreakdown]] | None:
        """Use LLM to semantically rerank top candidates.

        The LLM is constrained to only reorder the provided candidate IDs; any
        hallucinated ID outside the candidate pool is discarded (see
        ``last_llm_rerank_audit``). The blend weight between the rule score and
        the LLM position score is configurable via ``rerank.llm_weight`` so the
        LLM's influence on the final ranking can be tuned without code changes.
        """
        query = (
            parse_result.get("raw_text")
            or parse_result.get("normalized_query")
            or parse_result.get("business_scenario")
            or ""
        )
        pool_size = int(self.rerank_config.get("candidate_pool", 30))
        top_candidates = scored[:pool_size]
        tail_candidates = scored[pool_size:]
        candidates_str = ""
        for i, (m, s, breakdown) in enumerate(top_candidates):
            name = m.get("model_name", "")
            mid = m.get("model_id", "")
            desc = m.get("description", "")
            tags_s = ", ".join(m.get("tags", []))
            # KG-RAG: surface structured model knowledge (the same facts the
            # knowledge graph indexes on) so the LLM can rank on semantic fit
            # rather than guessing from opaque numeric IDs.
            scenarios = m.get("business_scenario", [])
            scenarios_s = "、".join(scenarios[:3]) if isinstance(scenarios, list) else str(scenarios)
            segments = m.get("customer_segment", m.get("applicable_customers", []))
            segments_s = "、".join(segments[:3]) if isinstance(segments, list) else ""
            capability = m.get("model_capability", [])
            capability_s = "、".join(capability[:3]) if isinstance(capability, list) else ""
            outputs = m.get("output_fields", [])
            outputs_s = "、".join(outputs[:4]) if isinstance(outputs, list) else ""
            boundary = str(m.get("applicable_conditions") or m.get("applicable_boundary") or "")[:120]
            retrieval_score = round(getattr(breakdown, "hybrid_retrieval_match", 0.0), 1)
            candidates_str += (
                f"{i+1}. {mid} - {name}\n"
                f"   场景: {scenarios_s}\n"
                f"   客群: {segments_s}\n"
                f"   能力: {capability_s}\n"
                f"   输出: {outputs_s}\n"
                f"   适用边界: {boundary}\n"
                f"   检索匹配: {retrieval_score}\n"
                f"   tags: {tags_s}\n"
                f"   description: {desc}\n"
            )
        system = (
            "你是银行模型市场推荐专家。请根据用户业务需求，对候选模型按语义匹配度从高到低排序。"
            "判断依据：模型的适用场景、客群、能力、输出和适用边界是否覆盖用户需求。"
            "只能对提供的候选模型 ID 重新排序，禁止编造任何不在候选列表中的模型 ID。"
            "ranked必须包含相关性最高的指定数量候选ID，每个ID恰好出现一次。"
            "只输出合法 JSON：{\"ranked\": [\"ID1\", \"ID2\", ...]}"
        )
        required_ranked_count = min(
            len(top_candidates),
            max(5, int(self.rerank_config.get("required_ranked_count", 10))),
        )
        candidate_ids_preview = [m.get("model_id", "") for m, _, _ in top_candidates]
        local_scores = [float(score) for _, score, _ in top_candidates]
        local_score_min = min(local_scores) if local_scores else 0.0
        local_score_max = max(local_scores) if local_scores else 0.0
        user = (
            f"User demand: {query}\n\n"
            f"Allowed candidate IDs: {json.dumps(candidate_ids_preview, ensure_ascii=False)}\n"
            f"Return exactly the top {required_ranked_count} IDs from this allowed list.\n\n"
            f"Candidates:\n{candidates_str}"
        )
        id_map = {m.get("model_id", ""): (m, s, b) for m, s, b in top_candidates}
        candidate_ids = list(id_map)
        cache_key = hashlib.sha256(
            (
                str(query)
                + "\0"
                + "\0".join(candidate_ids)
                + "\0"
                + str(required_ranked_count)
                + "\0"
                + str(getattr(self.llm, "model", ""))
                + "\0candidate-minmax-v1\0"
                + str(self.rerank_config.get("llm_weight", 0.35))
            ).encode("utf-8")
        ).hexdigest()
        cache_enabled = bool(self.rerank_config.get("cache_enabled", True))
        cached = self._llm_rerank_cache.get(cache_key) if cache_enabled else None
        if cached:
            cached_ranked = cached["ranked_ids"]
            cached_completed = cached["completed_ids"]
            self.last_llm_rerank_audit = {
                "attempted": False,
                "success": True,
                "status": "cache_hit",
                "cache_hit": True,
                "repair_attempted": False,
                "required_ranked_count": required_ranked_count,
                "valid_ranked_count": len(cached_ranked),
                "valid_ranked_ids": cached_ranked,
                "invalid_ranked_ids": [],
                "missing_ranked_ids": [],
                "unranked_candidate_ids": [mid for mid in candidate_ids if mid not in cached_ranked],
                "candidate_count": len(id_map),
                "trace_ids": [],
                "provider": str(getattr(self.llm, "provider", "")),
                "model": str(getattr(self.llm, "model", "")),
                "local_score_normalization": "candidate_minmax_v1",
                "local_score_min": round(local_score_min, 4),
                "local_score_max": round(local_score_max, 4),
            }
            return self._apply_llm_ranking(cached_completed, id_map, top_candidates, tail_candidates)

        trace_ids: list[str] = []
        repair_attempted = False
        llm_cache_context = {
            "candidate_ids": candidate_ids,
            "required_ranked_count": required_ranked_count,
            "config_hash": cache_key,
        }
        result = self.llm.chat_json(
            system,
            user,
            prompt_version="rerank-candidate-minmax-v1",
            cache_context=llm_cache_context,
        )
        trace_id = str(getattr(self.llm, "last_trace_id", "") or "")
        if trace_id:
            trace_ids.append(trace_id)
        ranked_ids, invalid_ids = self._validated_ranked_ids(result, id_map)
        missing_count = max(0, required_ranked_count - len(ranked_ids))

        if missing_count and int(self.rerank_config.get("repair_attempts", 1)) > 0:
            repair_attempted = True
            repair_system = (
                "你负责修复银行模型候选排序JSON。只能使用允许的ID，必须返回全部ID且每个恰好一次。"
                "只输出JSON：{\"ranked\":[...]}"
            )
            repair_user = (
                f"用户需求：{query}\n"
                f"允许的ID：{json.dumps(candidate_ids, ensure_ascii=False)}\n"
                f"必须返回数量：{required_ranked_count}\n"
                f"上次有效ID：{json.dumps(ranked_ids, ensure_ascii=False)}\n"
                f"上次非法ID：{json.dumps(invalid_ids, ensure_ascii=False)}\n"
                f"还缺少数量：{missing_count}"
            )
            repaired = self.llm.chat_json(
                repair_system,
                repair_user,
                prompt_version="rerank-repair-v1",
                cache_context={**llm_cache_context, "invalid_ids": invalid_ids},
            )
            repair_trace = str(getattr(self.llm, "last_trace_id", "") or "")
            if repair_trace and repair_trace not in trace_ids:
                trace_ids.append(repair_trace)
            repaired_ids, repaired_invalid = self._validated_ranked_ids(repaired, id_map)
            if len(repaired_ids) > len(ranked_ids):
                ranked_ids = repaired_ids
            invalid_ids.extend(mid for mid in repaired_invalid if mid not in invalid_ids)
            missing_count = max(0, required_ranked_count - len(ranked_ids))

        if invalid_ids:
            logger.warning("LLM rerank returned illegal model IDs and they were discarded: %s", invalid_ids)
        if not ranked_ids:
            self.last_llm_rerank_audit = {
                "attempted": True,
                "success": False,
                "status": "fallback",
                "fallback_reason": "no_valid_ranked_ids",
                "cache_hit": False,
                "repair_attempted": repair_attempted,
                "required_ranked_count": required_ranked_count,
                "valid_ranked_count": 0,
                "valid_ranked_ids": [],
                "invalid_ranked_ids": invalid_ids,
                "missing_ranked_ids": candidate_ids,
                "candidate_count": len(id_map),
                "trace_ids": trace_ids,
                "provider": str(getattr(self.llm, "provider", "")),
                "model": str(getattr(self.llm, "model", "")),
                "local_score_normalization": "candidate_minmax_v1",
                "local_score_min": round(local_score_min, 4),
                "local_score_max": round(local_score_max, 4),
            }
            return None
        completed_ids = ranked_ids + [mid for mid in candidate_ids if mid not in ranked_ids]
        unranked_ids = [mid for mid in candidate_ids if mid not in ranked_ids]
        status = "complete" if not missing_count else "partial"
        if status == "complete" and cache_enabled:
            self._llm_rerank_cache[cache_key] = {
                "ranked_ids": ranked_ids,
                "completed_ids": completed_ids,
            }
        self.last_llm_rerank_audit = {
            "attempted": True,
            "success": status == "complete",
            "status": status,
            "cache_hit": False,
            "repair_attempted": repair_attempted,
            "required_ranked_count": required_ranked_count,
            "valid_ranked_count": len(ranked_ids),
            "valid_ranked_ids": ranked_ids,
            "invalid_ranked_ids": invalid_ids,
            "missing_ranked_ids": [] if not missing_count else unranked_ids,
            "unranked_candidate_ids": unranked_ids,
            "candidate_count": len(id_map),
            "trace_ids": trace_ids,
            "provider": str(getattr(self.llm, "provider", "")),
            "model": str(getattr(self.llm, "model", "")),
            "local_score_normalization": "candidate_minmax_v1",
            "local_score_min": round(local_score_min, 4),
            "local_score_max": round(local_score_max, 4),
        }
        return self._apply_llm_ranking(completed_ids, id_map, top_candidates, tail_candidates)

    @staticmethod
    def _validated_ranked_ids(
        result: dict[str, Any] | None,
        id_map: dict[str, tuple[dict[str, Any], float, ScoreBreakdown]],
    ) -> tuple[list[str], list[str]]:
        if not result or not isinstance(result.get("ranked"), list):
            return [], []
        ranked_ids: list[str] = []
        invalid_ids: list[str] = []
        for raw_id in result.get("ranked", []):
            mid = str(raw_id).strip()
            if not mid or mid in ranked_ids:
                continue
            if mid not in id_map:
                if mid not in invalid_ids:
                    invalid_ids.append(mid)
                continue
            ranked_ids.append(mid)
        return ranked_ids, invalid_ids

    def _apply_llm_ranking(
        self,
        ranked_ids: list[str],
        id_map: dict[str, tuple[dict[str, Any], float, ScoreBreakdown]],
        top_candidates: list[tuple[dict[str, Any], float, ScoreBreakdown]],
        tail_candidates: list[tuple[dict[str, Any], float, ScoreBreakdown]],
    ) -> list[tuple[dict[str, Any], float, ScoreBreakdown]]:
        reranked: list[tuple[dict[str, Any], float, ScoreBreakdown]] = []
        llm_weight = float(self.rerank_config.get("llm_weight", 0.35))
        rule_weight = 1.0 - llm_weight
        local_scores = [float(score) for _, score, _ in top_candidates]
        local_low = min(local_scores) if local_scores else 0.0
        local_high = max(local_scores) if local_scores else 0.0
        local_span = local_high - local_low
        for idx, mid in enumerate(ranked_ids):
            model, score, breakdown = id_map[mid]
            llm_score = max(60.0, 100.0 - idx * 5.0)
            normalized_local_score = (
                100.0
                if local_span <= 1e-9
                else 100.0 * (float(score) - local_low) / local_span
            )
            updated_breakdown = self._copy_breakdown_with_llm(breakdown, llm_score)
            updated_score = round(
                min(100.0, normalized_local_score * rule_weight + llm_score * llm_weight),
                1,
            )
            reranked.append((model, updated_score, updated_breakdown))
        seen = set(ranked_ids)
        reranked.extend(item for item in top_candidates if item[0].get("model_id", "") not in seen)
        # The configured blend must control the final order. Previously the
        # method returned raw LLM order even though it calculated blended
        # scores, which made llm_weight misleading and allowed unstable output
        # to overwrite strong deterministic evidence.
        reranked.sort(key=lambda item: (-item[1], item[0].get("model_id", "")))
        reranked.extend(tail_candidates)
        return reranked

    @staticmethod
    def _copy_breakdown_with_llm(breakdown: ScoreBreakdown, llm_score: float) -> ScoreBreakdown:
        """Return score breakdown with LLM rerank score attached."""
        payload = breakdown.model_dump() if hasattr(breakdown, "model_dump") else breakdown.dict()
        payload["llm_semantic_match"] = round(llm_score, 1)
        return ScoreBreakdown(**payload)


def _domain_display(domain: str) -> str:
    """Convert domain key to display name."""
    mapping = {
        "credit_risk": "信贷风控",
        "customer_marketing": "客户营销",
        "operation_management": "运营管理",
    }
    return mapping.get(domain, domain)


_recommendation_service: ModelRecommendationService | None = None


def get_model_recommendation_service() -> ModelRecommendationService:
    """Return the process-wide recommendation service used by API and readiness checks."""
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = ModelRecommendationService()
    return _recommendation_service


def reset_model_recommendation_service_for_tests() -> None:
    """Reset the process-wide recommendation service in isolated tests."""
    global _recommendation_service
    _recommendation_service = None
