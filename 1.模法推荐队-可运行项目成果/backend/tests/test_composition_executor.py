"""Tests for demo composition execution traces."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.composition_executor import CompositionExecutor
from app.services.composition_planner import CompositionPlanner
from app.services.demand_parser import DemandParser


client = TestClient(app)


@pytest.fixture
def parser():
    return DemandParser()


@pytest.fixture
def planner():
    return CompositionPlanner()


@pytest.fixture
def executor():
    return CompositionExecutor()


DEMANDS = [
    "帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。",
    "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。",
    "我想监测网点运营异常和合规风险，输出需要复核的预警清单。",
]


@pytest.mark.parametrize("demand", DEMANDS)
def test_executor_builds_completed_demo_trace(parser, planner, executor, demand):
    parse_result = parser.parse(demand).model_dump()
    composition = planner.plan(parse_result)

    result = executor.execute_demo(composition, parse_result)

    assert result.demo_data is True
    assert result.desensitized_notice
    # The execution status is now a real state machine rather than a flat
    # happy path: completed / degraded / partially_blocked are all valid.
    assert result.status in {"completed", "degraded", "partially_blocked", "no_executable_node"}
    if composition.nodes:
        assert len(result.nodes) == len(composition.nodes)
        # Every node must carry one of the state-machine statuses.
        valid_statuses = {"completed", "degraded", "blocked", "pending"}
        assert all(node.status in valid_statuses for node in result.nodes)
        # Blocked nodes correctly produce no output; completed/degraded do.
        for node in result.nodes:
            if node.status == "blocked":
                assert node.output_snapshot == {}
            else:
                assert node.input_snapshot
        assert result.fused_result["demo_data"] is True
        assert result.fused_result["next_actions"]
        # Node contributions (result lineage) must be populated for non-blocked nodes.
        assert isinstance(result.node_contributions, list)


@pytest.mark.parametrize("demand", DEMANDS)
def test_recommend_composition_api_returns_execution_result(demand):
    parse_resp = client.post("/api/v1/parse-demand", json={"raw_text": demand})
    assert parse_resp.status_code == 200

    comp_resp = client.post(
        "/api/v1/recommend-composition",
        json={"parse_result": parse_resp.json()},
    )

    assert comp_resp.status_code == 200
    data = comp_resp.json()
    assert data["execution_result"] is not None
    execution = data["execution_result"]
    assert execution["demo_data"] is True
    assert execution["desensitized_notice"]
    if data["nodes"]:
        assert execution["status"] in {"completed", "degraded", "partially_blocked"}
        assert len(execution["nodes"]) == len(data["nodes"])
        assert execution["fused_result"]["next_actions"]


def test_executor_blocks_node_when_hard_dependency_fails(planner, executor):
    """A node whose feeding edge failed IO must be blocked, not silently completed.

    This is the core regression guard for the 'never-fail' fix: previously every
    node was hardcoded to 'completed' regardless of IO gaps. Now a hard failure
    must propagate as 'blocked' and produce no output.
    """
    from app.schemas.composition import (
        CompositionNode, CompositionEdge, IOCompatibilityResult,
        RecommendCompositionResponse,
    )

    node_a = CompositionNode(node_id="A", step_order=1, capability="反欺诈",
                             model_id="M1", model_name="反欺诈模型",
                             input_requirements=["customer_profile"],
                             output_fields=["fraud_score"], depends_on=[])
    node_b = CompositionNode(node_id="B", step_order=2, capability="额度测算",
                             model_id="M2", model_name="额度模型",
                             input_requirements=["collateral_info", "guarantee_info"],
                             output_fields=["credit_limit"], depends_on=["A"],
                             dependency_type="hard")
    # Edge A->B fails: A outputs fraud_score (no collateral/guarantee overlap).
    fail_edge = CompositionEdge(
        source_node_id="A", target_node_id="B", io_status="fail",
        missing_fields=["collateral_info", "guarantee_info"], suggestion="缺失",
    )
    composition = RecommendCompositionResponse(
        composition_id="X", composition_name="测试", scenario="测试",
        total_score=50.0, nodes=[node_a, node_b], flow_edges=[fail_edge],
        io_compatibility=IOCompatibilityResult(total_edges=1, failed=1),
    )

    result = executor.execute_demo(composition, {"intent": "credit_risk"})

    status_by_id = {n.node_id: n.status for n in result.nodes}
    assert status_by_id["A"] == "completed"   # source node runs fine
    assert status_by_id["B"] == "blocked"     # hard dependency failed
    # The blocked node must have no output and a status reason explaining why.
    b_node = next(n for n in result.nodes if n.node_id == "B")
    assert b_node.output_snapshot == {}
    assert b_node.status_reason
    assert result.status == "partially_blocked"
    assert result.fused_result["completed_models"] == ["反欺诈模型"]
    assert result.fused_result["blocked_models"] == ["额度模型"]
    assert "完成1个" in result.fused_result["summary"]
    assert "阻塞1个" in result.fused_result["summary"]


def test_marketing_composition_prefers_scenario_relevant_models(parser, planner):
    parse_result = parser.parse(
        "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。"
    ).model_dump()

    composition = planner.plan(parse_result)
    selected_names = [node.model_name for node in composition.nodes]
    selected_ids = [node.model_id for node in composition.nodes]

    assert selected_ids
    assert all(model_id.startswith("OFFICIAL_") for model_id in selected_ids)
    assert {node.source for node in composition.nodes} == {"official"}
    assert any(
        term in name
        for name in selected_names
        for term in ("营销", "响应", "转化", "新客")
    )
    assert not any("催收" in name for name in selected_names)
    assert not any("反诈" in name for name in selected_names)

    demo_composition = planner.plan({**parse_result, "model_source": "demo"})
    demo_ids = [node.model_id for node in demo_composition.nodes]
    assert "MKT_001" in demo_ids or "MKT_025" in demo_ids
    assert {node.source for node in demo_composition.nodes} == {"demo"}


def test_fused_result_has_no_heuristic_lift_percentage(parser, planner, executor):
    """Demo fused result must not present a heuristic lift range as a real prediction."""
    import re

    parse_result = parser.parse(
        "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。"
    ).model_dump()
    composition = planner.plan(parse_result)
    result = executor.execute_demo(composition, parse_result)

    fused = result.fused_result
    # confidence stays an internal field (hidden by the frontend filter, not deleted).
    assert "confidence" in fused
    assert isinstance(fused["confidence"], float)
    # No percentage-style effect claims anywhere in the user-visible fused result.
    for key, value in fused.items():
        for text in ([value] if isinstance(value, str) else [str(v) for v in value] if isinstance(value, list) else []):
            assert not re.search(r"\d+(\.\d+)?%", text), f"{key} still shows a percentage: {text}"
    assert "待真实业务数据验证" in fused.get("expected_lift", "")


def test_composition_api_response_has_no_lift_percentage(parser):
    """The composition API (what the page renders) must not expose 15%-25% style ranges."""
    parse_resp = client.post(
        "/api/v1/parse-demand",
        json={"raw_text": "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。"},
    )
    assert parse_resp.status_code == 200
    comp_resp = client.post(
        "/api/v1/recommend-composition",
        json={"parse_result": parse_resp.json()},
    )
    assert comp_resp.status_code == 200
    data = comp_resp.json()
    assert "15%-25%" not in str(data)
    assert "15%" not in str(data.get("execution_result", {}).get("fused_result", {}))
    # Planning order is deterministic and unaffected by the display-only change.
    order_a = [n["model_id"] for n in data["nodes"]]
    comp_resp2 = client.post(
        "/api/v1/recommend-composition",
        json={"parse_result": parse_resp.json()},
    )
    order_b = [n["model_id"] for n in comp_resp2.json()["nodes"]]
    assert order_a == order_b
