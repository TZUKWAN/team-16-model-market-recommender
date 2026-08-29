"""Tests for the unified LLM client."""

import json

import httpx

from app.services.llm_client import LLMClient
from app.services.llm_trace_service import LLMTraceService


def test_bigmodel_full_endpoint_is_used_as_is():
    client = LLMClient(
        provider="bigmodel",
        api_key="test-key",
        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        model="glm-4.7-flash",
    )

    assert client.available is True
    assert client.endpoint == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert client.status()["llm_provider"] == "bigmodel"
    assert client.status()["llm_model"] == "glm-4.7-flash"


def test_bigmodel_base_path_adds_chat_completions():
    client = LLMClient(
        provider="bigmodel",
        api_key="test-key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4.7-flash",
    )

    assert client.endpoint == "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def test_mock_provider_disables_llm_even_with_key():
    client = LLMClient(provider="mock", api_key="test-key", model="glm-4.7-flash")

    assert client.available is False
    assert client.chat("system", "user") is None


def test_status_does_not_expose_api_key():
    client = LLMClient(
        provider="bigmodel",
        api_key="very-secret-test-key",
        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        model="glm-4.7-flash",
    )

    rendered = str(client.status())
    assert "very-secret-test-key" not in rendered
    assert client.status()["llm_api_key_configured"] is True


def test_successful_chat_writes_non_sensitive_trace(monkeypatch, tmp_path):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "LLM_SMOKE_OK"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
            request=request,
        )
    trace_service = LLMTraceService(trace_dir=tmp_path, enabled=True)
    client = LLMClient(
        provider="bigmodel",
        api_key="very-secret-test-key",
        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        model="glm-4.7-flash",
        trace_service=trace_service,
        transport=httpx.MockTransport(handler),
    )

    result = client.chat("system prompt", "user message")

    assert result == "LLM_SMOKE_OK"
    trace_text = trace_service.trace_path.read_text(encoding="utf-8")
    assert "very-secret-test-key" not in trace_text
    assert "system prompt" not in trace_text
    assert "user message" not in trace_text
    assert "LLM_SMOKE_OK" not in trace_text
    trace = json.loads(trace_text)
    assert trace["success"] is True
    assert trace["provider"] == "bigmodel"
    assert trace["model"] == "glm-4.7-flash"
    assert trace["total_tokens"] == 5


def _client(handler, *, retries=2):
    return LLMClient(
        provider="openai",
        api_key="test-secret-key",
        base_url="https://llm.test/v1",
        model="Qwen3.5-122B-A10B",
        max_retries=retries,
        transport=httpx.MockTransport(handler),
        trace_service=LLMTraceService(enabled=False),
    )


def test_success_cache_key_includes_prompt_version_and_context():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=request)

    client = _client(handler)
    assert client.chat("system", "user", prompt_version="p1", cache_context={"candidate_ids": ["M1"]}) == "ok"
    assert client.chat("system", "user", prompt_version="p1", cache_context={"candidate_ids": ["M1"]}) == "ok"
    assert len(calls) == 1
    assert client.last_call_status["status"] == "cache_hit"
    assert client.chat("system", "user", prompt_version="p2", cache_context={"candidate_ids": ["M1"]}) == "ok"
    assert len(calls) == 2


def test_retryable_429_and_500_then_success(monkeypatch):
    statuses = [429, 500, 200]
    monkeypatch.setattr("time.sleep", lambda _: None)

    def handler(request):
        status = statuses.pop(0)
        payload = {"choices": [{"message": {"content": "recovered"}}]} if status == 200 else {}
        return httpx.Response(status, json=payload, request=request)

    client = _client(handler, retries=2)
    assert client.chat("system", "retry") == "recovered"
    assert client.last_call_status["attempts"] == 3


def test_read_timeout_is_not_retried_to_avoid_duplicate_billing():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("read timeout", request=request)

    client = _client(handler, retries=3)
    assert client.chat("system", "timeout") is None
    assert calls == 1
    assert client.last_call_status["reason"] == "ReadTimeout"


def test_invalid_json_and_empty_response_are_honest_failures():
    responses = [
        lambda request: httpx.Response(200, text="not-json", request=request),
        lambda request: httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}, request=request),
    ]
    for response in responses:
        client = _client(response, retries=2)
        assert client.chat("system", "invalid") is None
        assert client.last_call_status["status"] == "fallback"
        assert client.last_call_status["attempts"] == 1


def test_circuit_opens_and_half_open_success_recovers():
    failing_calls = 0

    def fail(request):
        nonlocal failing_calls
        failing_calls += 1
        return httpx.Response(500, json={}, request=request)

    client = _client(fail, retries=0)
    client.circuit_failure_threshold = 2
    assert client.chat("system", "one") is None
    assert client.chat("system", "two") is None
    assert client.status()["llm_circuit_state"] == "open"
    assert client.chat("system", "blocked") is None
    assert failing_calls == 2
    assert client.last_call_status["reason"] == "circuit_open"

    def recover(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "back"}}]}, request=request)

    client._transport = httpx.MockTransport(recover)
    client._opened_at -= client.circuit_open_seconds + 1
    assert client.status()["llm_circuit_state"] == "half_open"
    assert client.chat("system", "probe") == "back"
    assert client.status()["llm_circuit_state"] == "closed"
