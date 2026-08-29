"""Desensitized demo result sample library."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.repositories.model_asset_repository import ModelAssetRepository, get_model_asset_repository
from app.services.compliance_service import get_compliance_service


DEMO_NOTICE = "本结果为脱敏演示数据，不代表真实生产客户、账户、机构或模型输出。"


class DemoResultService:
    """Load and serve domain-specific desensitized demo model results."""

    def __init__(
        self,
        data_dir: Path | None = None,
        repository: ModelAssetRepository | None = None,
    ) -> None:
        settings = get_settings()
        self.data_dir = data_dir or settings.DATA_DIR / "demo_results"
        self.repository = repository or get_model_asset_repository()
        self._rows_by_type: dict[str, list[dict[str, Any]]] = {}

    def result_for_model(self, model_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a complete demo result payload for a model."""
        result_type = self.result_type_for_model(model_id)
        rows = self.rows(result_type)
        payload = {
            "model_id": model_id,
            "demo_data": True,
            "result_type": result_type,
            "input_echo_keys": sorted((payload or {}).keys()),
            "desensitized_notice": DEMO_NOTICE,
            "rows": rows,
        }
        return get_compliance_service().apply_to_result_payload(payload)

    def result_schema_for_model(self, model_id: str) -> dict[str, Any]:
        """Return result schema aligned to the model's demo result type."""
        result_type = self.result_type_for_model(model_id)
        return {
            "type": "object",
            "required": [
                "demo_data",
                "result_type",
                "desensitized_notice",
                "rows",
                "compliance_notice",
                "usage_boundary",
            ],
            "properties": {
                "demo_data": {"type": "boolean", "description": "是否为脱敏演示数据"},
                "result_type": {"type": "string", "description": "演示结果类型"},
                "desensitized_notice": {"type": "string", "description": "脱敏说明"},
                "compliance_notice": {"type": "string", "description": "合规提示"},
                "usage_boundary": {"type": "string", "description": "用途边界"},
                "compliance": {"type": "object", "description": "合规治理元信息"},
                "rows": {
                    "type": "array",
                    "items": self.row_schema(result_type),
                },
            },
        }

    def rows(self, result_type: str) -> list[dict[str, Any]]:
        """Return demo rows for a result type."""
        if result_type not in self._rows_by_type:
            self._rows_by_type[result_type] = self._load_rows(result_type)
        return [dict(row) for row in self._rows_by_type[result_type]]

    def result_type_for_model(self, model_id: str) -> str:
        """Map model id/domain to one of risk/marketing/operation result types."""
        model = self.repository.get_model(model_id) or {}
        domain = str(model.get("domain") or "").lower()
        if domain == "credit_risk" or model_id.startswith("RISK_"):
            return "risk"
        if domain == "customer_marketing" or model_id.startswith("MKT_"):
            return "marketing"
        return "operation"

    @staticmethod
    def row_schema(result_type: str) -> dict[str, Any]:
        common = {
            "demo_data": {"type": "boolean"},
            "desensitized_notice": {"type": "string"},
        }
        if result_type == "risk":
            properties = {
                **common,
                "customer_id_masked": {"type": "string"},
                "risk_score": {"type": "number"},
                "risk_level": {"type": "string"},
                "reason_code": {"type": "string"},
                "suggested_action": {"type": "string"},
            }
        elif result_type == "marketing":
            properties = {
                **common,
                "customer_id_masked": {"type": "string"},
                "product": {"type": "string"},
                "conversion_probability": {"type": "number"},
                "priority": {"type": "string"},
                "touch_channel": {"type": "string"},
            }
        else:
            properties = {
                **common,
                "subject_masked": {"type": "string"},
                "warning_type": {"type": "string"},
                "probability": {"type": "number"},
                "suggested_action": {"type": "string"},
            }
        return {
            "type": "object",
            "required": list(properties.keys()),
            "properties": properties,
        }

    def _load_rows(self, result_type: str) -> list[dict[str, Any]]:
        file_map = {
            "risk": "risk_results.jsonl",
            "marketing": "marketing_results.jsonl",
            "operation": "operation_results.jsonl",
        }
        path = self.data_dir / file_map.get(result_type, "operation_results.jsonl")
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    row["demo_data"] = True
                    row.setdefault("desensitized_notice", DEMO_NOTICE)
                    rows.append(row)
        return rows


_demo_result_service: DemoResultService | None = None


def get_demo_result_service() -> DemoResultService:
    """Return singleton demo result service."""
    global _demo_result_service
    if _demo_result_service is None:
        _demo_result_service = DemoResultService()
    return _demo_result_service


def reset_demo_result_service_for_tests() -> None:
    """Reset singleton demo result service in tests."""
    global _demo_result_service
    _demo_result_service = None
