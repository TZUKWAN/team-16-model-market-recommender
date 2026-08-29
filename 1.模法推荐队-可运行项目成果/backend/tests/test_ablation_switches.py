"""Tests for the ablation switches (use_llm / use_keyword_rules).

These switches let evaluation scripts reproduce a pure-rule baseline and
measure each component's isolated contribution. They must:
- preserve legacy behavior when both switches are None (default),
- fully bypass LLM calls when use_llm=False,
- fully bypass hardcoded keyword rules when use_keyword_rules=False.
"""

from app.services.demand_parser import DemandParser
from app.services.recommender import ModelRecommendationService


# --- fakes ------------------------------------------------------------------

class CallCountingLLM:
    """Records every LLM call so tests can assert none happen in rule-only mode."""

    available = True
    last_trace_id = "trace-x"

    def __init__(self):
        self.chat_json_calls = 0
        self.chat_calls = 0

    def chat_json(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.chat_json_calls += 1
        return None  # treat as unavailable-ish: forces fallback paths

    def chat(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.chat_calls += 1
        return None


# --- parser switch ----------------------------------------------------------

def test_parser_use_llm_false_forces_rule_source():
    """use_llm=False must route through rule parsing regardless of LLM availability."""
    parser = DemandParser()
    parser.llm = CallCountingLLM()  # available=True, but we force rule path
    result = parser.parse("我想做农户小额贷款的贷前准入风控", use_llm=False)
    assert result.parse_source == "rule"
    # The rule path must not have invoked the LLM at all.
    assert parser.llm.chat_json_calls == 0


def test_parser_use_llm_none_preserves_legacy_when_unavailable():
    """When the LLM is unavailable, legacy behavior is rule parsing."""
    parser = DemandParser()
    parser.llm = CallCountingLLM()
    parser.llm.available = False
    result = parser.parse("识别小微企业贷款中的欺诈申请")
    assert result.parse_source == "rule"


# --- recommender switches ---------------------------------------------------

def _recommend_parse_result():
    return {
        "intent": "credit_risk",
        "raw_text": "房贷贷前准入评分卡",
        "business_scenario": "房贷贷前准入评分",
        "tags": ["credit_risk", "application_scoring"],
        "customer_segment": ["mortgage_borrower"],
        "expected_outputs": ["approval_score"],
        "model_source": "official",
    }


def test_recommend_use_llm_false_makes_no_llm_calls():
    """use_llm=False must bypass both rerank and reason LLM paths."""
    service = ModelRecommendationService()
    counting = CallCountingLLM()
    service.llm = counting
    service.explainer.llm = counting  # share the counter with the explainer

    result = service.recommend(_recommend_parse_result(), top_k=3, use_llm=False)

    assert len(result.recommendations) > 0
    # No LLM call should have happened in the pure-rule baseline.
    assert counting.chat_json_calls == 0


def test_recommend_can_run_rerank_without_llm_reason_calls():
    """Evaluation may use one constrained rerank path without polishing five reasons."""
    service = ModelRecommendationService()
    counting = CallCountingLLM()
    service.llm = counting
    service.explainer.llm = counting

    result = service.recommend(
        _recommend_parse_result(),
        top_k=3,
        use_llm=True,
        use_llm_reason=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=True,
    )

    assert result.recommendations
    assert counting.chat_json_calls >= 1
    assert counting.chat_calls == 0


def test_recommend_use_keyword_rules_false_bypasses_keyword_adjustment():
    """use_keyword_rules=False must make _keyword_alignment_adjustment return 0."""
    service = ModelRecommendationService()
    model = service.models[0]
    # With keyword rules ON, a mortgage query may yield a non-zero adjustment;
    # with the switch OFF the adjustment must be exactly 0.0.
    pr_on = {**_recommend_parse_result(), "__kw_active": True}
    pr_off = {**_recommend_parse_result(), "__kw_active": False}
    on_val = service._keyword_alignment_adjustment(model, pr_on)
    off_val = service._keyword_alignment_adjustment(model, pr_off)
    assert off_val == 0.0
    # The on-value need not be non-zero for every model, but the switch must
    # deterministically zero it out when disabled.
    if on_val != 0.0:
        assert off_val != on_val


def test_recommend_default_flags_unchanged_behavior():
    """Passing neither switch (None) must keep legacy behavior intact."""
    service = ModelRecommendationService()
    # Should not raise and should return a normal response; the default path
    # is whatever self.llm.available decides.
    result = service.recommend(_recommend_parse_result(), top_k=3)
    assert result.request_id.startswith("rec-")
    assert len(result.recommendations) > 0
