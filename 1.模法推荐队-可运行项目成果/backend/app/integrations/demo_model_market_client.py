"""Desensitized demo model-market adapter."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from app.integrations.base import ModelMarketClientBase
from app.repositories.model_asset_repository import ModelAssetRepository, get_model_asset_repository
from app.services.demo_result_service import DemoResultService, get_demo_result_service


class DemoModelMarketClient(ModelMarketClientBase):
    """Local demo adapter that never claims to be a real upstream connection."""

    adapter_name = "demo"

    def __init__(
        self,
        repository: ModelAssetRepository | None = None,
        result_service: DemoResultService | None = None,
    ) -> None:
        self.repository = repository or get_model_asset_repository()
        self.result_service = result_service or get_demo_result_service()
        self._task_results: dict[str, dict[str, Any]] = {}

    @property
    def connected(self) -> bool:
        return False

    def status(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "connected": False,
            "demo_mode": True,
            "configured": True,
            "message": "使用本地脱敏演示适配器，未连接真实模型市场。",
        }

    async def get_model_detail(self, model_id: str) -> dict[str, Any]:
        model = self.repository.get_model(model_id) or {
            "model_id": model_id,
            "model_name": model_id,
            "result_schema": {"type": "object", "properties": {}},
        }
        return {
            **model,
            "demo_data": True,
            "demo_notice": "本响应来自本地脱敏演示适配器，不代表真实模型市场 API。",
        }

    async def invoke_model(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = self._task_id(model_id, payload)
        result = self.result_service.result_for_model(model_id, payload)
        self._task_results[task_id] = result
        return {
            "task_id": task_id,
            "model_id": model_id,
            "status": "completed",
            "demo_data": True,
            "submitted_at": self._now(),
            "message": "本地脱敏演示调用已完成。",
            "result": result,
        }

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "status": "completed",
            "demo_data": True,
            "updated_at": self._now(),
        }

    async def get_model_result(self, task_id: str) -> dict[str, Any]:
        result = self._task_results.get(task_id)
        if result is None:
            result = {
                "demo_data": True,
                "result_type": "operation",
                "desensitized_notice": "未找到本地任务上下文，返回通用运营脱敏演示结果。",
                "rows": self.result_service.rows("operation"),
            }
        return {
            "task_id": task_id,
            "status": "completed",
            "demo_data": True,
            "result": result,
        }

    async def get_result_schema(self, model_id: str) -> dict[str, Any]:
        return {
            "model_id": model_id,
            "demo_data": True,
            "result_schema": self.result_service.result_schema_for_model(model_id),
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _task_id(model_id: str, payload: dict[str, Any]) -> str:
        raw = f"{model_id}:{repr(sorted((payload or {}).items()))}".encode("utf-8")
        return f"demo-task-{hashlib.sha1(raw).hexdigest()[:12]}"
