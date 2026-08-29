"""Tests for LLM-backed demand parsing configuration and fallback."""

from app.services.demand_parser import DemandParser
from app.services.llm_client import LLMClient


class FakeLLM:
    available = True
    last_trace_id = "llm_demand_trace"

    def __init__(self, payload):
        self.payload = payload
        self.last_call_status = {"status": "fallback", "reason": "ReadTimeout"} if payload is None else {"status": "success"}

    def chat_json(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.system_prompt = system_prompt
        self.user_message = user_message
        self.temperature = temperature
        self.call_options = kwargs
        return self.payload


def test_bigmodel_defaults_resolve_openai_compatible_endpoint():
    client = LLMClient(provider="bigmodel", api_key="test-key")

    assert client.available is True
    assert client.endpoint == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert client.model == "glm-4.7-flash"
    assert client.status()["llm_api_key_configured"] is True


def test_qwen_request_body_disables_thinking_for_json_stability():
    client = LLMClient(provider="openai", api_key="test-key", base_url="http://example.test/v1", model="Qwen3.5-122B-A10B")

    body = client._request_body("system", "user", 0.1)

    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_llm_demand_parser_normalizes_json_to_local_schema():
    parser = DemandParser()
    parser.llm = FakeLLM({
        "intent": "customer_marketing",
        "intent_confidence": 0.93,
        "business_scenario": "县域新客首贷营销",
        "business_stage": "marketing",
        "customer_segment": ["县域新客"],
        "product_type": ["首贷"],
        "risk_type": [],
        "expected_outputs": ["营销名单", "转化概率"],
        "constraints": ["内部授权触达"],
        "data_conditions": ["客户画像", "交易流水"],
        "tags": ["customer_marketing", "conversion_prediction", "not_a_tag"],
        "need_clarification": False,
        "clarification_questions": [],
        "user_confirmable_summary": "为县域新客生成首贷营销名单。",
    })

    result = parser.parse("帮我筛一批县域新客做首贷营销。")

    assert result.parse_source == "llm"
    assert result.llm_enabled is True
    assert result.llm_trace_id == "llm_demand_trace"
    assert result.intent == "customer_marketing"
    assert "conversion_prediction" in result.tags
    assert "not_a_tag" not in result.tags


def test_llm_demand_parser_falls_back_when_llm_returns_none():
    parser = DemandParser()
    parser.llm = FakeLLM(None)

    result = parser.parse("贷后逾期预警名单")
    assert result.llm_fallback_reason == "ReadTimeout"

    assert result.parse_source == "hybrid_fallback"
    assert result.llm_enabled is True
    assert result.intent == "credit_risk"
