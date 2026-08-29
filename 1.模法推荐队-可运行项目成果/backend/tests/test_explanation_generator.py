"""Tests for LLM-backed recommendation explanation generation."""

from app.services.explanation_generator import ExplanationGenerator


class FakeLLM:
    available = True
    last_trace_id = "exp_trace"

    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, system_prompt, user_message, temperature=0.1):
        self.system_prompt = system_prompt
        self.user_message = user_message
        self.temperature = temperature
        return self.payload


MODEL = {
    "model_id": "MKT_001",
    "model_name": "县域新客首贷转化预测模型",
    "model_capability": ["conversion_prediction"],
    "input_fields_required": ["customer_profile", "transaction_flow"],
    "output_fields": ["conversion_probability", "ranked_list"],
    "business_scenario": ["县域新客首贷营销"],
    "applicable_conditions": "适用于县域新客首贷营销。",
    "unsuitable_conditions": "不适用于无授权营销。",
    "compliance_boundary": "需遵守客户授权边界。",
    "tags": ["customer_marketing", "conversion_prediction"],
    "performance_metrics": {"auc": 0.93},
}


def test_llm_explanation_uses_valid_model_field_reference():
    generator = ExplanationGenerator(FakeLLM({
        "recommendation_reason": "县域新客首贷转化预测模型可输出conversion_probability，适合首贷营销名单排序。",
        "business_explanation": "",
        "data_requirements": "",
        "unsuitable_boundary": "",
        "compliance_tip": "",
    }))

    result = generator.generate_recommendation_reason(MODEL, {"business_scenario": "县域新客首贷营销"}, "规则理由")

    assert result["source"] == "llm"
    assert "conversion_probability" in result["reason"]
    assert result["trace_id"] == "exp_trace"
    assert "performance_metrics" not in generator.llm.user_message


def test_llm_explanation_without_real_field_falls_back():
    generator = ExplanationGenerator(FakeLLM({
        "recommendation_reason": "这个模型效果提升80%，非常适合所有场景。",
    }))

    result = generator.generate_recommendation_reason(MODEL, {"business_scenario": "县域新客首贷营销"}, "规则理由")

    assert result["source"] == "fallback"
    assert result["reason"] == "规则理由"


def test_rule_reason_used_when_llm_unavailable():
    llm = FakeLLM(None)
    llm.available = False
    generator = ExplanationGenerator(llm)

    result = generator.generate_recommendation_reason(MODEL, {}, "规则理由")

    assert result["source"] == "rule"
    assert result["reason"] == "规则理由"


def test_llm_explanation_with_internal_score_falls_back():
    generator = ExplanationGenerator(FakeLLM({
        "recommendation_reason": "县域新客首贷转化预测模型综合评分95分，可输出conversion_probability。",
    }))

    result = generator.generate_recommendation_reason(MODEL, {}, "规则理由")

    assert result["source"] == "fallback"
    assert result["reason"] == "规则理由"
