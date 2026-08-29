"""Tests for non-sensitive LLM tracing."""

import json

from app.services.llm_trace_service import LLMTraceService
from app.core.request_context import correlation_id_var, request_id_var


def test_trace_record_excludes_raw_prompt_response_and_secret(tmp_path):
    service = LLMTraceService(trace_dir=tmp_path, enabled=True)
    secret = "very-secret-test-key"
    request_token = request_id_var.set("request-trace-001")
    correlation_token = correlation_id_var.set("workflow-trace-001")

    try:
        record = service.record(
            trace_id="llm_test",
            operation="chat",
            provider="bigmodel",
            model="glm-4.7-flash",
            endpoint="https://open.bigmodel.cn/api/paas/v4/chat/completions",
            system_prompt=f"system prompt {secret}",
            user_message="user asks for a recommendation",
            success=True,
            started_at=service.start_timer(),
            response_text="LLM response content",
            status_code=200,
            attempts=1,
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
    finally:
        request_id_var.reset(request_token)
        correlation_id_var.reset(correlation_token)

    assert record is not None
    assert record["endpoint_host"] == "open.bigmodel.cn"
    assert record["success"] is True
    assert record["total_tokens"] == 15
    assert record["request_id"] == "request-trace-001"
    assert record["correlation_id"] == "workflow-trace-001"

    text = service.trace_path.read_text(encoding="utf-8")
    assert secret not in text
    assert "system prompt" not in text
    assert "user asks" not in text
    assert "LLM response content" not in text
    loaded = json.loads(text)
    assert loaded["system_prompt_hash"]
    assert loaded["user_message_hash"]
    assert loaded["response_hash"]


def test_trace_can_be_disabled(tmp_path):
    service = LLMTraceService(trace_dir=tmp_path, enabled=False)
    result = service.record(
        trace_id="llm_disabled",
        operation="chat",
        provider="bigmodel",
        model="glm-4.7-flash",
        endpoint="https://open.bigmodel.cn/api/paas/v4/chat/completions",
        system_prompt="system",
        user_message="user",
        success=False,
        started_at=service.start_timer(),
    )

    assert result is None
    assert not service.trace_path.exists()
