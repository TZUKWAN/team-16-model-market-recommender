"""Effect estimation for side-by-side model comparison."""

from __future__ import annotations

from typing import Any

from app.schemas.comparison import EffectEstimate
from app.services.data_readiness_service import DataReadinessService


class EffectEstimator:
    """Estimate expected lift without calling a real model."""

    def __init__(self) -> None:
        self.data_readiness = DataReadinessService()

    def estimate_effect(self, model: dict[str, Any], parse_result: dict[str, Any]) -> EffectEstimate:
        readiness = self.data_readiness.diagnose(model, parse_result)
        readiness_factor = max(0.0, min(1.0, readiness.readiness_score / 100.0))
        segment_factor = self._segment_match_factor(model, parse_result)
        metrics = model.get("performance_metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        metric_source = self._metric_source(model, metrics)
        base_lift = self._base_lift_pct(metrics)
        estimated = round(base_lift * readiness_factor * segment_factor, 1)
        band_width = round(base_lift * (1 - readiness_factor) * 0.6, 1)
        low = round(max(0.0, estimated - band_width), 1)
        high = round(estimated + band_width, 1)
        coverage = round(self._coverage_pct(model, parse_result, segment_factor, readiness_factor), 1)

        # Evidence level: only verified metrics + good readiness can reach "medium".
        # "high" requires verified metrics AND readiness >= 70%.
        if metric_source == "verified" and readiness_factor >= 0.7:
            evidence_level = "high"
        elif metric_source in ("verified", "draft") and readiness_factor >= 0.4:
            evidence_level = "medium"
        else:
            evidence_level = "low"

        # When data readiness is 0 or key fields missing, suppress precise high lift.
        if readiness_factor < 0.05:
            estimated = min(estimated, 5.0)
            evidence_level = "low"

        not_for_decision = evidence_level == "low" or readiness_factor < 0.1

        verification_status = {
            "verified": "指标来自可核验来源",
            "draft": "指标为推断草案，待人工复核",
            "missing": "无结构化性能指标，使用启发式默认基线（未验证）",
        }[metric_source]

        assumptions = self._assumptions(model, readiness.readiness_score, metric_source, segment_factor)

        return EffectEstimate(
            estimated_lift_pct=estimated,
            coverage_pct=coverage,
            confidence_band_pct=[low, high],
            data_readiness_factor=round(readiness_factor, 2),
            segment_match_factor=round(segment_factor, 2),
            basis=self._basis(model, readiness.readiness_score, base_lift),
            metric_source=metric_source,
            verification_status=verification_status,
            evidence_level=evidence_level,
            assumptions=assumptions,
            not_for_decision=not_for_decision,
        )

    def _metric_source(self, model: dict[str, Any], metrics: dict[str, Any]) -> str:
        """Determine whether performance metrics are verified, draft, or missing."""
        # Check if metrics dict has any numeric performance values.
        perf_keys = {"auc", "ks", "lift_top10pct", "precision_top20pct", "accuracy", "f1", "recall"}
        has_numeric_perf = any(
            k in metrics and isinstance(metrics[k], (int, float))
            for k in perf_keys
        )
        if has_numeric_perf:
            metric_field = model.get("field_provenance", {}).get("performance_metrics", {})
            verification = str(metric_field.get("verification") or "")
            if verification == "source_verified":
                return "verified"
            if verification:
                return "draft"
            # Check if the model source marks these as verified or draft.
            # Official catalog models have inferred metrics (draft); demo models with real metrics are verified.
            source = str(model.get("source", "")).lower()
            metric_provenance = str(model.get("metric_provenance", "")).lower()
            if metric_provenance == "verified":
                return "verified"
            return "draft"
        return "missing"

    def _assumptions(
        self,
        model: dict[str, Any],
        readiness_score: float,
        metric_source: str,
        segment_factor: float,
    ) -> list[str]:
        assumptions = [
            "预估假设历史指标在当前客群上仍然有效",
            "实际效果取决于数据质量、特征工程和模型部署方式",
        ]
        if metric_source == "draft":
            assumptions.append("模型性能指标为推断草案，实际值可能显著不同")
        if metric_source == "missing":
            assumptions.append("缺少结构化性能指标，使用保守默认基线")
        if readiness_score < 40:
            assumptions.append(f"数据就绪度较低（{readiness_score}%），预估不确定性高")
        if segment_factor < 0.85:
            assumptions.append("目标客群与模型设计客群匹配度有限")
        return assumptions

    def _base_lift_pct(self, metrics: dict[str, Any]) -> float:
        numeric = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
        if "lift_top10pct" in numeric:
            return max(8.0, min(65.0, (float(numeric["lift_top10pct"]) - 1.0) * 22.0))
        if "auc" in numeric:
            return max(8.0, min(45.0, (float(numeric["auc"]) - 0.5) * 80.0))
        if "ks" in numeric:
            return max(6.0, min(35.0, float(numeric["ks"]) * 55.0))
        if "precision_top20pct" in numeric:
            return max(6.0, min(35.0, float(numeric["precision_top20pct"]) * 42.0))
        if "accuracy" in numeric:
            return max(5.0, min(30.0, (float(numeric["accuracy"]) - 0.5) * 55.0))
        return 10.0

    def _coverage_pct(
        self,
        model: dict[str, Any],
        parse_result: dict[str, Any],
        segment_factor: float,
        readiness_factor: float,
    ) -> float:
        metrics = model.get("performance_metrics", {})
        if isinstance(metrics, dict) and isinstance(metrics.get("coverage"), (int, float)):
            base = float(metrics["coverage"]) * 100
        else:
            model_segments = self._normalize_segments(model.get("customer_segment", []))
            query_segments = self._normalize_segments(parse_result.get("customer_segment", []))
            base = 72.0 if not query_segments else 45.0 + 35.0 * segment_factor
            if model_segments and not query_segments:
                base = 68.0
        return max(10.0, min(100.0, base * (0.85 + readiness_factor * 0.15)))

    def _segment_match_factor(self, model: dict[str, Any], parse_result: dict[str, Any]) -> float:
        model_segments = self._normalize_segments(model.get("customer_segment", []))
        query_segments = self._normalize_segments(parse_result.get("customer_segment", []))
        if not query_segments:
            return 1.0
        if not model_segments:
            return 0.75
        overlap = len(model_segments & query_segments)
        if overlap == 0:
            return 0.75
        return min(1.1, 0.85 + 0.25 * overlap / max(len(query_segments), 1))

    def _normalize_segments(self, values: Any) -> set[str]:
        if values is None:
            raw: list[str] = []
        elif isinstance(values, list):
            raw = [str(v).strip() for v in values if str(v).strip()]
        else:
            raw = [str(values).strip()] if str(values).strip() else []

        aliases = {
            "农户": "farmer",
            "农村": "farmer",
            "小微": "small_micro_enterprise",
            "小微企业": "small_micro_enterprise",
            "企业": "corporate",
            "对公": "corporate",
            "个人": "individual",
            "对私": "individual",
            "高价值": "high_net_worth",
            "高净值": "high_net_worth",
            "中高端": "high_net_worth",
            "新客": "new_customer",
            "存量": "existing_customer",
            "老客": "existing_customer",
            "流失": "churned_customer",
            "沉睡": "dormant_customer",
        }
        result: set[str] = set()
        for item in raw:
            lower = item.lower()
            result.add(lower)
            for key, normalized in aliases.items():
                if key.lower() in lower:
                    result.add(normalized)
        return result

    def _basis(self, model: dict[str, Any], readiness_score: float, base_lift: float) -> list[str]:
        metrics = model.get("performance_metrics", {})
        keys = ", ".join(str(k) for k in list(metrics.keys())[:5]) if isinstance(metrics, dict) else ""
        return [
            f"历史指标映射基础提升约 {round(base_lift, 1)}%",
            f"数据就绪度 {readiness_score}%",
            f"使用指标字段：{keys or '无结构化指标，使用保守默认值'}",
        ]
