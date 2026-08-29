"""Data readiness diagnosis for model recommendation landing."""

from __future__ import annotations

from typing import Any

from app.schemas.recommendation import DataReadinessReport


class DataReadinessService:
    """Diagnoses required data, missing fields, and confidence impact."""

    def diagnose(self, model: dict[str, Any], parse_result: dict[str, Any]) -> DataReadinessReport:
        required = self._as_list(model.get("input_fields_required"))
        optional = self._as_list(model.get("input_fields_optional"))
        declared = self._as_list(parse_result.get("data_conditions"))
        available_required = [field for field in required if self._soft_contains(field, declared)]
        missing_required = [field for field in required if field not in available_required]
        missing_optional = [field for field in optional if not self._soft_contains(field, declared)]

        required_score = 1.0 if not required else len(available_required) / len(required)
        optional_score = 1.0 if not optional else (len(optional) - len(missing_optional)) / len(optional)
        readiness = round((required_score * 0.8 + optional_score * 0.2) * 100, 1)

        return DataReadinessReport(
            readiness_score=readiness,
            required_fields=required + optional,
            available_fields=available_required,
            missing_required_fields=missing_required,
            missing_optional_fields=missing_optional[:8],
            confidence_impact=self._confidence_impact(readiness, missing_required),
            action_items=self._action_items(missing_required, missing_optional),
            substitution_notes=self._substitution_notes(model, missing_required),
        )

    def _confidence_impact(self, readiness: float, missing_required: list[str]) -> str:
        if not missing_required and readiness >= 80:
            return "数据条件较完整，可进入模型接入验证。"
        if missing_required and readiness < 50:
            return "关键输入缺失较多，建议优先补齐数据或选择输入要求更低的替代模型。"
        return "存在部分输入缺口，模型可先试算，但正式上线前需补齐或确认替代字段。"

    def _action_items(self, missing_required: list[str], missing_optional: list[str]) -> list[str]:
        items: list[str] = []
        for field in missing_required[:5]:
            items.append(f"补齐必需字段：{field}")
        for field in missing_optional[:3]:
            items.append(f"确认可选增强字段：{field}")
        if not items:
            items.append("保持当前数据口径，并在试运行阶段监控字段质量。")
        return items

    def _substitution_notes(self, model: dict[str, Any], missing_required: list[str]) -> list[str]:
        if not missing_required:
            return ["当前模型输入条件基本满足，可优先验证该模型。"]
        capability = "、".join(self._as_list(model.get("model_capability"))[:2]) or "相近能力"
        return [
            f"若短期无法补齐{missing_required[0]}，可优先查看具备{capability}但输入字段更少的替代模型。",
            "替代模型仍需满足同一业务场景、输出类型和合规边界。",
        ]

    def _soft_contains(self, field: str, declared: list[str]) -> bool:
        field_lower = field.lower()
        for item in declared:
            item_lower = item.lower()
            if field_lower in item_lower or item_lower in field_lower:
                return True
        return False

    def _as_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []
