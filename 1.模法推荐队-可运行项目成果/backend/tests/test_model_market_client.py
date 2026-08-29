"""Tests for model-market integration adapters."""

import pytest

from app.integrations.base import ModelMarketNotConfiguredError, ModelMarketUpstreamError
from app.integrations.demo_model_market_client import DemoModelMarketClient
from app.integrations.http_model_market_client import HttpModelMarketClient
from app.integrations.model_market_client import build_model_market_client


@pytest.mark.asyncio
async def test_demo_adapter_returns_explicit_demo_detail_and_result_schema():
    client = DemoModelMarketClient()

    detail = await client.get_model_detail("MKT_001")
    schema = await client.get_result_schema("MKT_001")
    invoke = await client.invoke_model("MKT_001", {"customer_profile": {"age": 35}})
    status = client.status()

    assert client.connected is False
    assert status["demo_mode"] is True
    assert detail["model_id"] == "MKT_001"
    assert detail["demo_data"] is True
    assert schema["demo_data"] is True
    assert schema["result_schema"]["type"] == "object"
    assert invoke["demo_data"] is True
    assert invoke["task_id"].startswith("demo-task-")


@pytest.mark.asyncio
async def test_http_adapter_unconfigured_raises_clear_error():
    client = HttpModelMarketClient(base_url="", api_key="")

    assert client.connected is False
    assert client.status()["connected"] is False
    assert client.status()["base_url_configured"] is False
    with pytest.raises(ModelMarketNotConfiguredError):
        await client.invoke_model("MKT_001", {})


@pytest.mark.asyncio
async def test_http_adapter_upstream_error_does_not_fallback_to_demo():
    class FailingClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, headers=None, json=None):
            raise TimeoutError("network timeout")

    client = HttpModelMarketClient(
        base_url="https://model-market.example.test",
        api_key="test-key",
        client_factory=FailingClient,
    )

    assert client.configured is True
    assert client.connected is False
    with pytest.raises(ModelMarketUpstreamError):
        await client.get_model_detail("MKT_001")
    assert client.connected is False


def test_model_market_factory_selects_demo_and_http_modes():
    demo = build_model_market_client("demo")
    http = build_model_market_client("http")

    assert isinstance(demo, DemoModelMarketClient)
    assert isinstance(http, HttpModelMarketClient)
