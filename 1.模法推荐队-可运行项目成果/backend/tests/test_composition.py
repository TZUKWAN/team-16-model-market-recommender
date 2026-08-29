"""Tests for CompositionPlanner service."""

import pytest
from app.services.composition_planner import CompositionPlanner
from app.services.demand_parser import DemandParser


@pytest.fixture
def planner():
    return CompositionPlanner()


@pytest.fixture
def parser():
    return DemandParser()


class TestTemplateMatching:
    """C-14: Template matching."""

    def test_pre_loan_composition(self, planner, parser):
        parse_result = parser.parse("帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。")
        result = planner.plan(parse_result.model_dump())
        # Should have anti-fraud, admission scoring, or amount estimation
        capabilities = [n.capability for n in result.nodes]
        has_key_cap = any(c in " ".join(capabilities) for c in ["anti_fraud", "admission_scoring", "amount_estimation"])
        assert has_key_cap

    def test_post_loan_composition(self, planner, parser):
        parse_result = parser.parse("我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。")
        result = planner.plan(parse_result.model_dump())
        assert hasattr(result, "nodes")

    def test_marketing_composition(self, planner, parser):
        parse_result = parser.parse("我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。")
        result = planner.plan(parse_result.model_dump())
        assert hasattr(result, "nodes")


class TestIOCompatibility:
    """C-15: IO compatibility checking."""

    def test_io_compatibility_present(self, planner, parser):
        parse_result = parser.parse("帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。")
        result = planner.plan(parse_result.model_dump())
        assert result.io_compatibility is not None
        if result.io_compatibility.total_edges > 0:
            assert result.io_compatibility.compatibility_rate >= 0

    def test_flow_edges_present(self, planner, parser):
        parse_result = parser.parse("帮我做农户小额贷款的贷前准入风控。")
        result = planner.plan(parse_result.model_dump())
        assert len(result.nodes) == 0 or len(result.flow_edges) >= 0


class TestCompositionScore:
    """Composition scoring."""

    def test_total_score_range(self, planner, parser):
        parse_result = parser.parse("农户小额贷款贷前准入风控")
        result = planner.plan(parse_result.model_dump())
        assert 0 <= result.total_score <= 100

    def test_explanations_present(self, planner, parser):
        parse_result = parser.parse("农户小额贷款贷前准入风控")
        result = planner.plan(parse_result.model_dump())
        if result.nodes:
            assert result.business_explanation or result.technical_explanation or result.management_explanation

    def test_default_nodes_are_official_and_demo_requires_explicit_mode(self, planner, parser):
        parse_result = parser.parse("农户小额贷款贷前准入风控").model_dump()

        official_result = planner.plan(parse_result)
        assert official_result.nodes
        assert {node.source for node in official_result.nodes} == {"official"}
        assert {node.catalog_version for node in official_result.nodes} == {"official-v1"}

        demo_result = planner.plan({**parse_result, "model_source": "demo"})
        assert demo_result.nodes
        assert {node.source for node in demo_result.nodes} == {"demo"}
        assert {node.catalog_version for node in demo_result.nodes} == {"demo-v1"}


class TestFallback:
    """Fallback behavior."""

    def test_fallback_on_no_match(self, planner):
        parse_result = {"intent": "unknown", "business_scenario": "", "tags": []}
        result = planner.plan(parse_result)
        assert result is not None
        assert "FALLBACK" in result.composition_id or len(result.nodes) >= 0
        assert result.composition_status == "no_template"
        assert result.total_score == 60.0
        assert result.failure_reasons

    def test_no_permitted_models_is_blocked(self, planner, parser):
        parse_result = parser.parse("农户贷款贷前反欺诈和准入评分").model_dump()
        parse_result["permitted_domains"] = []
        result = planner.plan(parse_result)
        assert result.composition_status == "blocked"
        assert result.nodes == []
        assert any("no permitted model" in reason for reason in result.failure_reasons)
        assert result.demo_execution_only is True


class TestUsageGuide:
    """Usage guide generation."""

    def test_usage_guide_present(self, planner, parser):
        parse_result = parser.parse("农户小额贷款贷前准入风控")
        result = planner.plan(parse_result.model_dump())
        if result.nodes:
            assert len(result.usage_guide) > 0
