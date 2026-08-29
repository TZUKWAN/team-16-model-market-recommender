"""Tests for ModelRecommendationService."""

import pytest
from app.services.recommender import ModelRecommendationService
from app.services.demand_parser import DemandParser
from app.services.explanation_generator import ExplanationGenerator


@pytest.fixture
def service():
    return ModelRecommendationService()


@pytest.fixture
def parser():
    return DemandParser()


class TestModelRecall:
    """C-09: Model recall."""

    def test_recall_by_domain_marketing(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["customer_marketing"], "business_scenario": "客户营销"}
        result = service.recommend(parse_result, top_k=3)
        assert len(result.recommendations) > 0

    def test_recall_by_domain_credit(self, service):
        parse_result = {"intent": "credit_risk", "tags": ["credit_risk"], "business_scenario": "信贷风控"}
        result = service.recommend(parse_result, top_k=3)
        assert len(result.recommendations) > 0

    def test_recall_by_tags(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["county_new_customer", "conversion_prediction"]}
        result = service.recommend(parse_result, top_k=5)
        assert len(result.recommendations) > 0

    def test_recall_farmer_tags(self, service):
        parse_result = {"intent": "credit_risk", "tags": ["farmer", "anti_fraud", "admission_scoring"]}
        result = service.recommend(parse_result, top_k=5)
        assert len(result.recommendations) > 0


class TestScoring:
    """C-11: Multi-dimension scoring."""

    def test_score_breakdown_present(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["county_new_customer", "conversion_prediction"],
                        "business_scenario": "县域新客首贷营销"}
        result = service.recommend(parse_result, top_k=1)
        assert len(result.recommendations) > 0
        rec = result.recommendations[0]
        assert rec.score_breakdown is not None
        assert rec.total_score > 0
        assert "综合评分" not in rec.recommendation_reason
        assert str(rec.total_score) not in rec.recommendation_reason

    def test_scenario_match_scored(self, service):
        parse_result = {"intent": "credit_risk", "tags": ["farmer"],
                        "business_scenario": "农户小额贷款贷前准入"}
        result = service.recommend(parse_result, top_k=1)
        if result.recommendations:
            sb = result.recommendations[0].score_breakdown
            assert sb.scenario_match > 0

    def test_multi_dimension_scores(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["county_new_customer", "marketing"],
                        "business_scenario": "客户营销", "customer_segment": ["县域新客"],
                        "expected_outputs": ["转化概率"]}
        result = service.recommend(parse_result, top_k=1)
        if result.recommendations:
            sb = result.recommendations[0].score_breakdown
            assert sb.scenario_match >= 0
            assert sb.customer_match >= 0
            assert sb.data_match >= 0
            assert sb.output_match >= 0
            assert sb.performance >= 0
            assert sb.landing_experience >= 0
            assert sb.compliance >= 0


class TestEvidenceAndGaps:
    """C-12: Evidence, gaps, alternatives."""

    def test_evidence_cards_present(self, service):
        parse_result = {"intent": "credit_risk", "tags": ["farmer"], "business_scenario": "贷前风控"}
        result = service.recommend(parse_result, top_k=1)
        if result.recommendations:
            cards = result.recommendations[0].evidence_cards
            assert len(cards) >= 1
            assert all(card.evidence_type not in {"历史案例", "性能指标"} for card in cards)
            assert "AUC=" not in result.recommendations[0].recommendation_reason

    def test_alternative_models(self, service):
        parse_result = {"intent": "credit_risk", "tags": ["anti_fraud"]}
        result = service.recommend(parse_result, top_k=3)
        assert len(result.recommendations) > 0

    def test_unrecommended_examples(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["marketing"], "business_scenario": "客户营销"}
        result = service.recommend(parse_result, top_k=2)
        assert result.unrecommended_examples is not None
        assert all("评分" not in item.reason for item in result.unrecommended_examples)
        assert "评分" not in result.summary

    def test_required_data_present(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["county_new_customer", "conversion_prediction"]}
        result = service.recommend(parse_result, top_k=1)
        if result.recommendations:
            assert len(result.recommendations[0].required_data) >= 1

    def test_graph_scores_and_evidence_present(self, service):
        """Recommendations should include graph path and field compatibility evidence."""
        parse_result = {
            "intent": "customer_marketing",
            "tags": ["customer_marketing", "conversion_prediction", "first_loan"],
            "business_scenario": "县域新客首贷营销",
            "business_stage": "pre_marketing",
            "customer_segment": ["new_customer", "rural_area"],
            "expected_outputs": ["conversion_probability", "ranked_list"],
            "data_conditions": ["customer_profile", "transaction_flow"],
        }
        result = service.recommend(parse_result, top_k=3)
        assert result.recommendations

        top = result.recommendations[0]
        assert top.score_breakdown.graph_path_match > 0
        assert top.score_breakdown.field_compatibility > 0
        assert any(card.evidence_type == "知识图谱路径" for card in top.evidence_cards)

        explanations = ExplanationGenerator.generate_model_explanations(top, parse_result)
        assert "图谱路径" in explanations["technical"]
        assert "字段兼容" in explanations["technical"]
        assert "评分拆解" not in explanations["technical"]
        assert "综合匹配分" not in explanations["business"]


class TestTopK:
    """Top-K ranking."""

    def test_top_k_3(self, service):
        parse_result = {"intent": "customer_marketing", "tags": ["marketing"]}
        result = service.recommend(parse_result, top_k=3)
        assert len(result.recommendations) <= 3

    def test_ranking_order(self, service):
        parse_result = {"intent": "credit_risk", "tags": ["farmer", "anti_fraud"]}
        result = service.recommend(parse_result, top_k=5)
        scores = [r.total_score for r in result.recommendations]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Scores not descending: {scores}"


class TestDemoPaths:
    """C-15: Three demo paths."""

    def test_marketing_path(self, service, parser):
        parse_result = parser.parse("我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。")
        payload = parse_result.model_dump()
        payload["model_source"] = "demo"
        result = service.recommend(payload, top_k=5)
        model_ids = [r.model_id for r in result.recommendations]
        assert "MKT_001" in model_ids

    def test_credit_risk_path(self, service, parser):
        parse_result = parser.parse("帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。")
        payload = parse_result.model_dump()
        payload["model_source"] = "demo"
        result = service.recommend(payload, top_k=5)
        model_ids = [r.model_id for r in result.recommendations]
        has_risk = any("RISK" in mid for mid in model_ids)
        assert has_risk

    def test_post_loan_path(self, service, parser):
        parse_result = parser.parse("我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。")
        payload = parse_result.model_dump()
        payload["model_source"] = "demo"
        result = service.recommend(payload, top_k=5)
        assert len(result.recommendations) > 0

    def test_small_micro_risk_top5(self, service):
        """Test that small micro enterprise risk control returns relevant models."""
        parse_result = {
            "model_source": "demo",
            "intent": "credit_risk",
            "tags": ["credit_risk", "small_micro_enterprise", "admission_scoring", "anti_fraud"],
            "business_scenario": "小微企业贷款全流程风控",
            "customer_segment": ["小微企业"],
            "business_stage": "pre_loan",
            "expected_outputs": ["risk_score", "fraud_label"],
            "data_conditions": ["customer_profile", "business_operation"],
        }
        result = service.recommend(parse_result, top_k=5)
        model_ids = [r.model_id for r in result.recommendations]
        assert len(result.recommendations) > 0
        has_small_micro = any(mid in model_ids for mid in ["RISK_004", "RISK_006"])
        assert has_small_micro, f"Expected RISK_004 or RISK_006 in top5, got {model_ids}"

    def test_branch_traffic_top5(self, service):
        """Test that branch traffic prediction returns OPS models."""
        parse_result = {
            "model_source": "demo",
            "intent": "operation_management",
            "tags": ["operation_management", "early_warning"],
            "business_scenario": "网点运营",
            "customer_segment": ["individual"],
            "business_stage": "",
            "expected_outputs": ["predicted_traffic"],
        }
        result = service.recommend(parse_result, top_k=5)
        model_ids = [r.model_id for r in result.recommendations]
        assert len(result.recommendations) > 0
        has_ops = any("OPS" in mid for mid in model_ids)
        assert has_ops, f"Expected OPS model in top5, got {model_ids}"

    def test_aml_detection_top5(self, service):
        """Test that AML/suspicious transaction scenarios return relevant models.
        AML models in data: OPS_009, OPS_011 (反洗钱), RISK_015, RISK_023 (合规异常), RISK_006 (反欺诈+异常).
        """
        parse_result = {
            "model_source": "demo",
            "intent": "operation_management",
            "tags": ["operation_management", "anomaly_detection", "anti_money_laundering", "compliance_check"],
            "business_scenario": "反洗钱可疑交易监测",
            "customer_segment": ["individual", "corporate"],
            "business_stage": "",
            "expected_outputs": ["fraud_score", "risk_indicators"],
        }
        result = service.recommend(parse_result, top_k=5)
        assert len(result.recommendations) > 0
        model_ids = [r.model_id for r in result.recommendations]
        aml_relevant = ["OPS_009", "OPS_011", "RISK_015", "RISK_023", "RISK_006", "RISK_002", "OPS_027"]
        has_aml_relevant = any(mid in model_ids for mid in aml_relevant)
        assert has_aml_relevant, f"Expected AML-relevant model in top5, got {model_ids}"
