"""Factory for model-market integration adapters."""

from app.core.config import get_settings
from app.integrations.base import ModelMarketClientBase
from app.integrations.demo_model_market_client import DemoModelMarketClient
from app.integrations.http_model_market_client import HttpModelMarketClient


def build_model_market_client(mode: str | None = None) -> ModelMarketClientBase:
    """Build a model-market adapter from settings or an explicit mode."""
    settings = get_settings()
    adapter = (mode or settings.MODEL_MARKET_ADAPTER or "").lower().strip()
    if not adapter:
        adapter = "demo" if settings.ENABLE_MOCK else "real"
    if adapter in {"demo", "mock", "test"}:
        return DemoModelMarketClient()
    if adapter in {"real", "http"}:
        return HttpModelMarketClient(
            base_url=settings.MODEL_MARKET_BASE_URL,
            api_key=settings.MODEL_MARKET_API_KEY,
            timeout_seconds=settings.MODEL_MARKET_TIMEOUT_SECONDS,
        )
    raise ValueError(f"Unsupported MODEL_MARKET_ADAPTER: {adapter}")


_model_market_client: ModelMarketClientBase | None = None


def get_model_market_client() -> ModelMarketClientBase:
    """Return singleton model-market adapter."""
    global _model_market_client
    if _model_market_client is None:
        _model_market_client = build_model_market_client()
    return _model_market_client


def reset_model_market_client_for_tests() -> None:
    """Reset singleton in tests after environment/config changes."""
    global _model_market_client
    _model_market_client = None


model_market_client = get_model_market_client()
