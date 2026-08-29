"""Tests for DemandParser service."""

import pytest
from app.services.demand_parser import DemandParser


@pytest.fixture
def parser():
    return DemandParser()


class TestIntentIdentification:
    """C-04: Intent and domain recognition."""

    def test_marketing_intent(self, parser):
        result = parser.parse("我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。")
        assert result.intent == "customer_marketing"
        assert result.intent_confidence >= 0.3

    def test_credit_risk_intent_pre_loan(self, parser):
        result = parser.parse("帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。")
        assert result.intent == "credit_risk"
        assert result.intent_confidence >= 0.3

    def test_credit_risk_intent_post_loan(self, parser):
        result = parser.parse("我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。")
        assert result.intent == "credit_risk"

    def test_operation_intent(self, parser):
        result = parser.parse("预测一下这个月的网点客流，看看高峰期在什么时候。")
        assert result.intent == "operation_management"

    def test_ambiguous_query(self, parser):
        result = parser.parse("帮我看看有什么模型可以用。")
        assert result.intent in ("customer_marketing", "credit_risk", "operation_management")

    def test_fraud_query(self, parser):
        result = parser.parse("识别小微企业贷款中的欺诈申请。")
        assert result.intent == "credit_risk"

    def test_scoring_query(self, parser):
        result = parser.parse("能不能贷这个农户的贷款申请？")
        all_tags_str = "".join(result.tags)
        assert "admission_scoring" in all_tags_str or "评分" in "".join(result.tag_names)

    def test_conversion_query(self, parser):
        result = parser.parse("这批客户哪些容易转化？")
        all_tags_str = "".join(result.tags)
        assert "conversion_prediction" in all_tags_str or "转化" in "".join(result.tag_names)

    def test_short_query(self, parser):
        result = parser.parse("贷后预警")
        assert result.intent == "credit_risk"

    def test_empty_query(self, parser):
        result = parser.parse("")
        assert result.intent == "customer_marketing"

    def test_aml_money_laundering(self, parser):
        """Test anti-money laundering / suspicious transaction detection."""
        result = parser.parse("反洗钱可疑交易监测")
        assert result.intent in ("customer_marketing", "credit_risk", "operation_management")
        assert result.tag_names
        all_tags = set(result.tags)
        assert any(t in all_tags for t in ["anti_money_laundering", "anomaly_detection", "compliance_check", "anti_fraud"])

    def test_branch_traffic(self, parser):
        """Test branch traffic prediction and smart rostering."""
        result = parser.parse("网点客流预测和智能排班")
        assert result.intent == "operation_management"
        all_tags = set(result.tags)
        assert "operation_management" in all_tags
        assert any(t in all_tags for t in ["resource_optimization", "resource_planning", "daily_operation"])

    def test_customer_churn(self, parser):
        """Test customer churn warning and retention."""
        result = parser.parse("客户流失预警与挽留")
        all_tags = set(result.tags)
        assert any(t in all_tags for t in ["churn_prediction", "existing_customer", "churned_customer"])

    def test_small_micro_risk(self, parser):
        """Test small micro enterprise risk control."""
        result = parser.parse("小微企业贷款全流程风控")
        assert result.intent in ("credit_risk", "operation_management")
        all_tags = set(result.tags)
        assert "small_micro_enterprise" in all_tags

    def test_tag_names_present(self, parser):
        """Test that tag_names is populated alongside tags."""
        result = parser.parse("帮我筛一批县域新客做首贷营销给出转化概率高的名单")
        assert len(result.tag_names) > 0
        assert len(result.tags) == len(result.tag_names)

    def test_tags_are_keys_not_names(self, parser):
        """Test that tags field contains standard keys, not display names."""
        result = parser.parse("农户小额贷款贷前反欺诈")
        for tag in result.tags:
            assert not any(ch in tag for ch in ['\u98ce', '\u9669', '\u519c', '\u6237']) or tag in (
                "farmer", "anti_fraud", "pre_loan", "credit_risk",
                "admission_scoring", "amount_estimation", "default_prediction",
                "early_warning", "small_micro_enterprise", "individual",
                "corporate", "marketing", "county_new_customer",
            ), f"Tag '{tag}' looks like a display name, should be a key"

    def test_rule_parse_source_is_visible(self, parser):
        result = parser.parse("县域新客首贷营销")
        assert result.parse_source == "rule"
        assert result.llm_enabled is False

    def test_ambiguous_query_returns_structured_clarification_questions(self, parser):
        result = parser.parse("帮我看看有什么模型可以用。")

        assert result.need_clarification is True
        assert result.clarification_questions
        question = result.clarification_questions[0]
        assert question.question_id
        assert question.question_text
        assert question.slot
        assert isinstance(question.options, list)


class FakeLLM:
    available = True
    last_trace_id = "llm_test_trace"

    def __init__(self, payload):
        self.payload = payload

    def chat_json(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.last_system_prompt = system_prompt
        self.last_user_message = user_message
        return self.payload


class TestHybridLLMParsing:
    def test_llm_parse_success_is_schema_normalized(self, parser):
        parser.llm = FakeLLM({
            "intent": "credit_risk",
            "intent_confidence": 1.5,
            "business_scenario": "农户贷前反欺诈准入",
            "business_stage": "pre_loan",
            "customer_segment": ["农户"],
            "product_type": ["涉农贷款"],
            "risk_type": ["欺诈风险"],
            "expected_outputs": ["风险评分", "准入结论"],
            "constraints": ["仅供内部风控使用"],
            "data_conditions": ["征信报告", "交易流水"],
            "tags": ["信贷风控", "反欺诈", "not_a_real_tag"],
            "need_clarification": False,
            "clarification_questions": [],
            "user_confirmable_summary": "识别农户贷款申请中的欺诈和准入风险",
        })

        result = parser.parse("帮我判断农户贷款申请有没有欺诈风险，并给出准入评分。")

        assert result.parse_source == "llm"
        assert result.llm_enabled is True
        assert result.llm_trace_id == "llm_test_trace"
        assert result.intent == "credit_risk"
        assert result.intent_confidence == 1.0
        assert "anti_fraud" in result.tags
        assert "not_a_real_tag" not in result.tags
        assert len(result.tags) == len(result.tag_names)
        assert result.structured_filters["domain"] == "credit_risk"

    def test_llm_parse_invalid_intent_falls_back_to_rule_intent(self, parser):
        parser.llm = FakeLLM({
            "intent": "invalid_domain",
            "intent_confidence": 0.7,
            "business_scenario": "网点客流预测",
            "business_stage": "",
            "tags": [],
            "need_clarification": True,
            "clarification_questions": ["是否需要按网点输出高峰时段？"],
        })

        result = parser.parse("网点客流预测和智能排班")

        assert result.parse_source == "llm"
        assert result.intent == "operation_management"
        assert result.need_clarification is True
        assert result.clarification_questions
        assert result.clarification_questions[0].question_text

    def test_llm_failure_uses_hybrid_fallback(self, parser):
        parser.llm = FakeLLM(None)

        result = parser.parse("贷后逾期预警名单")

        assert result.parse_source == "hybrid_fallback"
        assert result.llm_enabled is True
        assert result.intent == "credit_risk"
