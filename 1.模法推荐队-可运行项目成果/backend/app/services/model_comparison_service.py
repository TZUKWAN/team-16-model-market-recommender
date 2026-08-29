"""Side-by-side model comparison service."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.model_asset_repository import get_model_asset_repository
from app.schemas.comparison import CompareModelsResponse, ModelComparisonItem
from app.services.data_readiness_service import DataReadinessService
from app.services.effect_estimator import EffectEstimator


class ModelComparisonService:
    """Build comparison matrices for selected model assets."""

    def __init__(self) -> None:
        self.repository = get_model_asset_repository()
        self.readiness = DataReadinessService()
        self.estimator = EffectEstimator()

    def compare(self, model_ids: list[str], parse_result: dict[str, Any]) -> CompareModelsResponse:
        unique_ids = list(dict.fromkeys(model_ids))[:5]
        items: list[ModelComparisonItem] = []
        for model_id in unique_ids:
            model = self.repository.get_model(model_id)
            if not model:
                continue
            data_readiness = self.readiness.diagnose(model, parse_result)
            effect = self.estimator.estimate_effect(model, parse_result)
            items.append(
                ModelComparisonItem(
                    model_id=model.get("model_id", ""),
                    model_name=model.get("model_name", ""),
                    domain=model.get("domain", ""),
                    customer_segment=self._as_list(model.get("customer_segment")),
                    input_fields_required=self._as_list(model.get("input_fields_required")),
                    output_fields=self._as_list(model.get("output_fields")),
                    performance_metrics=model.get("performance_metrics", {}) if isinstance(model.get("performance_metrics"), dict) else {},
                    applicable_conditions=str(model.get("applicable_conditions", "")),
                    unsuitable_conditions=str(model.get("unsuitable_conditions", "")),
                    compliance_boundary=str(model.get("compliance_boundary", "")),
                    data_readiness=data_readiness,
                    effect_estimate=effect,
                )
            )

        return CompareModelsResponse(
            request_id=f"cmp-{uuid.uuid4().hex[:8]}",
            items=items,
            matrix=self._matrix(items),
        )

    def _matrix(self, items: list[ModelComparisonItem]) -> list[dict[str, Any]]:
        return [
            self._row("适用边界", items, lambda i: i.applicable_conditions),
            self._row("慎用场景", items, lambda i: i.unsuitable_conditions),
            self._row("目标客群", items, lambda i: "、".join(i.customer_segment)),
            self._row("必需数据", items, lambda i: "、".join(i.input_fields_required)),
            self._row("主要输出", items, lambda i: "、".join(i.output_fields)),
            self._row("性能指标", items, lambda i: ", ".join(f"{k}={v}" for k, v in i.performance_metrics.items() if k != "metric_note") or "暂无"),
            self._row("数据就绪度", items, lambda i: "高" if i.data_readiness.readiness_score >= 70 else "中" if i.data_readiness.readiness_score >= 40 else "低"),
            self._row("预期提升", items, lambda i: "待验证"),
            self._row("覆盖率", items, lambda i: "待验证"),
            self._row("置信区间", items, lambda i: "启发式估计，非统计推断"),
            self._row("合规边界", items, lambda i: i.compliance_boundary),
        ]

    def _row(self, label: str, items: list[ModelComparisonItem], getter: Any) -> dict[str, Any]:
        values = {item.model_id: getter(item) for item in items}
        return {"dimension": label, "values": values}

    def _as_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [str(value).strip()] if str(value).strip() else []