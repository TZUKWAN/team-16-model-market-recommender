"""Tests for LLM semantic reranking with local candidate constraints."""

from app.schemas.recommendation import ScoreBreakdown
from app.services.recommender import ModelRecommendationService


class FakeRerankLLM:
    available = True
    last_trace_id = "llm_rerank_trace"

    def __init__(self, ranked):
        self.ranked = ranked
        self.calls = []

    def chat_json(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.calls.append({
            "system_prompt": system_prompt,
            "user_message": user_message,
            "temperature": temperature,
            "options": kwargs,
        })
        return {"ranked": self.ranked}


class SequenceRerankLLM(FakeRerankLLM):
    def __init__(self, responses):
        super().__init__([])
        self.responses = list(responses)

    def chat_json(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.calls.append({"system_prompt": system_prompt, "user_message": user_message, "options": kwargs})
        self.last_trace_id = f"trace_{len(self.calls)}"
        return self.responses.pop(0)


def _score_item(service: ModelRecommendationService, model_id: str, score: float):
    model = service.model_repository.get_model(model_id)
    assert model is not None
    breakdown = ScoreBreakdown(
        scenario_match=80,
        customer_match=70,
        data_match=60,
        output_match=75,
        graph_path_match=85,
        field_compatibility=80,
        performance=70,
        landing_experience=60,
        compliance=75,
    )
    return model, score, breakdown


def test_llm_rerank_discards_illegal_model_ids_and_keeps_candidate_set():
    service = ModelRecommendationService()
    service.llm = FakeRerankLLM(["MKT_002", "OFF_CATALOG_FAKE", "MKT_001", "MKT_002"])
    scored = [
        _score_item(service, "MKT_001", 88.0),
        _score_item(service, "MKT_002", 84.0),
        _score_item(service, "MKT_003", 80.0),
    ]
    parse_result = {
        "intent": "customer_marketing",
        "business_scenario": "县域新客首贷营销和存量客户交叉销售混合场景",
        "tags": ["customer_marketing", "conversion_prediction", "cross_selling"],
        "customer_segment": ["new_customer", "existing_customer"],
        "expected_outputs": ["conversion_probability", "ranked_list"],
    }

    reranked = service._semantic_rerank_with_llm(scored, parse_result)

    assert reranked is not None
    reranked_ids = [item[0]["model_id"] for item in reranked]
    assert set(reranked_ids[:2]) == {"MKT_001", "MKT_002"}
    assert "OFF_CATALOG_FAKE" not in reranked_ids
    assert set(reranked_ids) == {"MKT_001", "MKT_002", "MKT_003"}
    assert service.last_llm_rerank_audit["invalid_ranked_ids"] == ["OFF_CATALOG_FAKE"]
    assert service.last_llm_rerank_audit["valid_ranked_ids"] == ["MKT_002", "MKT_001"]
    by_id = {item[0]["model_id"]: item for item in reranked}
    assert by_id["MKT_002"][2].llm_semantic_match == 100.0
    assert by_id["MKT_001"][2].llm_semantic_match == 95.0
    assert service.llm.calls
    prompt = service.llm.calls[0]["user_message"]
    assert "User demand:" in prompt
    assert "tags:" in prompt
    assert "description:" in prompt
    assert "domain:" not in prompt
    assert "scenarios:" not in prompt
    assert "outputs:" not in prompt
    assert "applicable:" not in prompt


def test_recommend_response_keeps_rule_graph_llm_score_details():
    service = ModelRecommendationService()
    service.llm = FakeRerankLLM(["MKT_001", "MKT_002", "MKT_003"])
    parse_result = {
        "model_source": "demo",
        "intent": "customer_marketing",
        "business_scenario": "县域新客首贷营销",
        "business_stage": "pre_marketing",
        "tags": ["customer_marketing", "conversion_prediction", "first_loan"],
        "customer_segment": ["new_customer", "rural_area"],
        "expected_outputs": ["conversion_probability", "ranked_list"],
        "data_conditions": ["customer_profile", "transaction_flow"],
    }

    result = service.recommend(parse_result, top_k=2)

    assert result.recommendations
    top = result.recommendations[0]
    assert top.model_id == "MKT_001"
    assert top.rule_score > 0
    assert top.graph_score > 0
    assert top.llm_score > 0
    assert top.score_breakdown.llm_semantic_match > 0


def test_llm_rerank_repairs_incomplete_json_and_records_traces():
    service = ModelRecommendationService()
    service.llm = SequenceRerankLLM([
        None,
        {"ranked": ["MKT_003", "MKT_002", "MKT_001"]},
    ])
    scored = [
        _score_item(service, "MKT_001", 88.0),
        _score_item(service, "MKT_002", 84.0),
        _score_item(service, "MKT_003", 80.0),
    ]

    reranked = service._semantic_rerank_with_llm(scored, {"raw_text": "客户营销"})

    assert reranked is not None
    assert {item[0]["model_id"] for item in reranked} == {"MKT_001", "MKT_002", "MKT_003"}
    assert reranked[0][0]["model_id"] == "MKT_001"
    assert service.last_llm_rerank_audit["status"] == "complete"
    assert service.last_llm_rerank_audit["repair_attempted"] is True
    assert service.last_llm_rerank_audit["trace_ids"] == ["trace_1", "trace_2"]


def test_llm_rerank_cache_avoids_duplicate_calls():
    service = ModelRecommendationService()
    service.llm = FakeRerankLLM(["MKT_002", "MKT_001", "MKT_003"])
    scored = [
        _score_item(service, "MKT_001", 88.0),
        _score_item(service, "MKT_002", 84.0),
        _score_item(service, "MKT_003", 80.0),
    ]
    parse_result = {"raw_text": "客户营销"}

    first = service._semantic_rerank_with_llm(scored, parse_result)
    second = service._semantic_rerank_with_llm(scored, parse_result)

    assert first is not None and second is not None
    assert len(service.llm.calls) == 1
    assert service.last_llm_rerank_audit["status"] == "cache_hit"
    assert service.last_llm_rerank_audit["attempted"] is False


def test_llm_rerank_preserves_candidates_outside_prompt_pool():
    service = ModelRecommendationService()
    service.rerank_config["candidate_pool"] = 2
    service.llm = FakeRerankLLM(["MKT_002", "MKT_001"])
    scored = [
        _score_item(service, "MKT_001", 88.0),
        _score_item(service, "MKT_002", 84.0),
        _score_item(service, "MKT_003", 80.0),
    ]

    reranked = service._semantic_rerank_with_llm(scored, {"raw_text": "客户营销"})

    assert reranked is not None
    assert [item[0]["model_id"] for item in reranked] == ["MKT_001", "MKT_002", "MKT_003"]


def test_candidate_minmax_prevents_low_scale_local_score_from_being_overwritten():
    service = ModelRecommendationService()
    service.llm = FakeRerankLLM(["MKT_009", "MKT_018", "MKT_001"])
    scored = [
        _score_item(service, "MKT_001", 49.3),
        _score_item(service, "MKT_009", 15.0),
        _score_item(service, "MKT_018", 14.0),
    ]

    reranked = service._semantic_rerank_with_llm(
        scored,
        {"raw_text": "县域新客首贷营销，输出转化概率名单"},
    )

    assert reranked is not None
    assert reranked[0][0]["model_id"] == "MKT_001"
    assert service.last_llm_rerank_audit["local_score_normalization"] == "candidate_minmax_v1"
    assert service.last_llm_rerank_audit["local_score_min"] == 14.0
    assert service.last_llm_rerank_audit["local_score_max"] == 49.3
