"""Base contracts for model-market integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelMarketError(RuntimeError):
    """Base error for model-market integration failures."""


class ModelMarketNotConfiguredError(ModelMarketError):
    """Raised when the real model-market client lacks URL or credentials."""


class ModelMarketUpstreamError(ModelMarketError):
    """Raised when the upstream model-market API returns an error or is unreachable."""


class ModelMarketContractError(ModelMarketUpstreamError):
    """Raised when an upstream response violates the configured contract."""


class ModelMarketClientBase(ABC):
    """Unified async interface for model-market adapters."""

    adapter_name: str

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether this adapter is connected to a real upstream system."""

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Return non-sensitive adapter status."""

    @abstractmethod
    async def get_model_detail(self, model_id: str) -> dict[str, Any]:
        """Return model detail from the adapter."""

    @abstractmethod
    async def invoke_model(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke a model and return a synchronous result or task descriptor."""

    @abstractmethod
    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """Return async task status."""

    @abstractmethod
    async def get_model_result(self, task_id: str) -> dict[str, Any]:
        """Return async task result."""

    @abstractmethod
    async def get_result_schema(self, model_id: str) -> dict[str, Any]:
        """Return model result schema."""
