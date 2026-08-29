"""Compliance and sensitive-field governance service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings


DEFAULT_COMPLIANCE_NOTICE = "结果已按演示与最小必要原则默认脱敏，仅用于模型推荐、方案验证和人工复核参考。"


class ComplianceService:
    """Applies lightweight compliance metadata and masking to result payloads."""

    def __init__(self, field_path: Path | None = None) -> None:
        settings = get_settings()
        self.field_path = field_path or settings.DATA_DIR / "knowledge" / "data_fields.json"
        self.fields = self._load_fields()

    def compliance_profile_for_result_type(self, result_type: str) -> dict[str, Any]:
        if result_type == "risk":
            return {
                "result_type": result_type,
                "sensitivity_level": "high",
                "usage_boundary": "仅用于授信风控、人工复核和审批策略辅助，不得作为自动拒贷的唯一依据。",
                "allowed_usage": ["风险识别", "人工复核", "审批策略辅助", "模型效果回溯"],
                "prohibited_usage": ["直接外发客户名单", "未经授权跨机构共享", "作为唯一自动化决策依据"],
            }
        if result_type == "marketing":
            return {
                "result_type": result_type,
                "sensitivity_level": "medium",
                "usage_boundary": "仅用于授权营销客群筛选和触达优先级排序，不得绕过客户授权或偏好约束。",
                "allowed_usage": ["营销名单排序", "渠道触达计划", "活动效果评估"],
                "prohibited_usage": ["未经授权营销触达", "出售或外部共享名单", "超范围使用客户画像"],
            }
        return {
            "result_type": result_type,
            "sensitivity_level": "medium",
            "usage_boundary": "仅用于运营预警、合规复核和内部流程改进，不得替代人工核查结论。",
            "allowed_usage": ["运营预警", "合规复核", "流程改进", "工单分派"],
            "prohibited_usage": ["公开披露明细", "绕过复核直接问责", "跨机构无授权扩散"],
        }

    def apply_to_result_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        result_type = str(payload.get("result_type") or "operation")
        profile = self.compliance_profile_for_result_type(result_type)
        rows = payload.get("rows", [])
        masked_rows: list[dict[str, Any]] = []
        masked_fields: set[str] = set()

        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            masked_row, row_masked_fields = self.mask_row(row)
            masked_rows.append(masked_row)
            masked_fields.update(row_masked_fields)

        governed = dict(payload)
        if masked_rows:
            governed["rows"] = masked_rows
        governed["compliance_notice"] = DEFAULT_COMPLIANCE_NOTICE
        governed["usage_boundary"] = profile["usage_boundary"]
        governed["compliance"] = {
            **profile,
            "default_desensitized": True,
            "sensitive_fields_masked": sorted(masked_fields),
            "field_registry_loaded": bool(self.fields),
        }
        return governed

    def mask_row(self, row: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        masked = dict(row)
        masked_fields: list[str] = []
        for key, value in row.items():
            if self._should_mask(key, value):
                masked[key] = self._mask_value(value)
                masked_fields.append(key)
        return masked, masked_fields

    def field_sensitivity(self, field_key: str) -> str:
        field = self.fields.get(field_key)
        if field:
            return str(field.get("sensitivity", ""))
        return ""

    def _load_fields(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self.field_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {
            str(item.get("field_key", "")): item
            for item in data.get("fields", [])
            if item.get("field_key")
        }

    def _should_mask(self, key: str, value: Any) -> bool:
        lowered = key.lower()
        if lowered.endswith("_masked") or lowered in {"demo_data", "desensitized_notice"}:
            return False
        sensitive_markers = ["customer_id", "customer_name", "phone", "mobile", "account", "id_no", "address"]
        if any(marker in lowered for marker in sensitive_markers):
            return True
        if self.field_sensitivity(lowered) == "high":
            return True
        return False

    def _mask_value(self, value: Any) -> str:
        text = str(value)
        if len(text) <= 4:
            return "****"
        return f"{text[:2]}****{text[-2:]}"


_compliance_service: ComplianceService | None = None


def get_compliance_service() -> ComplianceService:
    global _compliance_service
    if _compliance_service is None:
        _compliance_service = ComplianceService()
    return _compliance_service
