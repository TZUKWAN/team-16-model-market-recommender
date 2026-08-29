"""HTTP adapter for a real external model-market API."""

from __future__ import annotations

from typing import Any, Callable

import httpx

from app.integrations.base import (
    ModelMarketContractError,
    ModelMarketClientBase,
    ModelMarketNotConfiguredError,
    ModelMarketUpstreamError,
)
from app.integrations.model_market_contract import CONTRACT_MODELS


class HttpModelMarketClient(ModelMarketClientBase):
    """OpenAPI-style HTTP adapter with explicit error behavior."""

    adapter_name = "http"

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout_seconds: int = 30,
        client_factory: Callable[..., httpx.AsyncClient] | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self._api_key = api_key or ""
        self.timeout_seconds = timeout_seconds
        self._client_factory = client_factory or httpx.AsyncClient
        self._connected = False

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._api_key)

    @property
    def connected(self) -> bool:
        return self._connected

    def status(self) -> dict[str, Any]:
        status = {
            "adapter": self.adapter_name,
            "connected": self.connected,
            "demo_mode": False,
            "configured": self.configured,
            "api_key_configured": bool(self._api_key),
            "base_url_configured": bool(self.base_url),
            "message": "真实模型市场适配器已配置。" if self.connected else "真实模型市场 URL 或凭证未配置。",
        }
        if self.connected:
            status["message"] = "Real model-market endpoint responded with a contract-valid payload."
        elif self.configured:
            status["message"] = "Real adapter is configured but connectivity is not yet verified."
        else:
            status["message"] = "Real model-market URL or credential is not configured."
        return status

    async def get_model_detail(self, model_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/models/{model_id}", contract="model_detail")

    async def invoke_model(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/models/{model_id}/invoke", json=payload, contract="invoke")

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tasks/{task_id}", contract="task_status")

    async def get_model_result(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/tasks/{task_id}/result", contract="model_result")

    async def get_result_schema(self, model_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/models/{model_id}/result-schema", contract="result_schema")

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        contract: str,
    ) -> dict[str, Any]:
        if not self.configured:
            raise ModelMarketNotConfiguredError("真实模型市场 URL 或 API Key 未配置。")
        url = f"{self.base_url}{path}"
        try:
            async with self._client_factory(timeout=self.timeout_seconds) as client:
                response = await client.request(method, url, headers=self._headers(), json=json)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise ModelMarketUpstreamError(f"模型市场 API 返回错误状态：{status_code}") from exc
        except Exception as exc:
            raise ModelMarketUpstreamError(f"模型市场 API 调用失败：{exc.__class__.__name__}") from exc
        if not isinstance(data, dict):
            raise ModelMarketUpstreamError("模型市场 API 返回非对象 JSON。")
        try:
            validated = CONTRACT_MODELS[contract].model_validate(data).model_dump()
            self._connected = True
            return validated
        except Exception as exc:
            self._connected = False
            raise ModelMarketContractError(
                f"model-market response violates {contract} contract: {exc.__class__.__name__}"
            ) from exc
