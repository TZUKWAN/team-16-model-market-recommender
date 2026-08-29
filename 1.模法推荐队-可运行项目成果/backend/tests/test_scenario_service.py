"""Tests for scenario library, matching, and script generation."""

from fastapi.testclient import TestClient

from app.main import app
from app.services.scenario_service import get_scenario_service, load_scenarios
from app.services.script_generator import get_script_generator

client = TestClient(app)


def test_scenarios_library_complete():
    scenarios = load_scenarios()
    assert len(scenarios) >= 30
    domains = {sc.domain for sc in scenarios}
    assert "credit_risk" in domains
    assert "customer_marketing" in domains
    assert "operation_management" in domains
    # each domain has at least 10 scenarios
    for domain in domains:
        assert sum(1 for sc in scenarios if sc.domain == domain) >= 10
    # all scenarios have required fields
    for sc in scenarios:
        assert sc.scenario_id
        assert sc.name
        assert sc.typical_scripts.marketing
        assert sc.applicable_models
        assert sc.keywords
        assert sc.compliance_notes


def test_scenario_match_credit_risk_demand():
    svc = get_scenario_service()
    resp = svc.match(
        {
            "raw_text": "帮我做农户小额贷款的贷前准入风控，识别欺诈风险",
            "intent": "credit_risk",
            "business_scenario": "农户小额贷款贷前准入",
        },
        top_k=3,
    )
    assert resp.total_scenarios >= 30
    assert len(resp.matches) == 3
    # top match should be the farmer loan scenario
    top = resp.matches[0]
    assert top.scenario.scenario_id == "SCN_001"
    assert top.match_score > 0
    assert "农户" in top.matched_keywords or "小额" in top.matched_keywords


def test_scenario_match_marketing_demand():
    svc = get_scenario_service()
    resp = svc.match(
        {
            "raw_text": "我想筛一批县域新客，做首贷营销",
            "intent": "customer_marketing",
        },
        top_k=3,
    )
    assert len(resp.matches) >= 1
    top = resp.matches[0]
    assert top.scenario.domain == "customer_marketing"
    assert top.match_score > 0


def test_scenario_match_operation_demand():
    svc = get_scenario_service()
    resp = svc.match(
        {
            "raw_text": "预测网点客流，优化柜员排班",
            "intent": "operation_management",
        },
        top_k=3,
    )
    assert len(resp.matches) >= 1
    top = resp.matches[0]
    assert top.scenario.domain == "operation_management"
    # should match the branch traffic scenario
    assert top.scenario.scenario_id == "SCN_021"


def test_get_scenario_by_id():
    svc = get_scenario_service()
    sc = svc.get_scenario("SCN_001")
    assert sc is not None
    assert sc.name
    assert sc.domain == "credit_risk"
    assert svc.get_scenario("SCN_NONEXIST") is None


def test_list_scenarios_by_domain():
    svc = get_scenario_service()
    all_scenarios = svc.list_scenarios()
    assert len(all_scenarios) >= 30
    risk_only = svc.list_scenarios("credit_risk")
    assert len(risk_only) >= 10
    assert all(sc.domain == "credit_risk" for sc in risk_only)
    marketing_only = svc.list_scenarios("customer_marketing")
    assert len(marketing_only) >= 10
    assert all(sc.domain == "customer_marketing" for sc in marketing_only)


def test_script_generation_fallback_in_mock_mode():
    """Without LLM configured, script generation degrades to typical scripts."""
    gen = get_script_generator()
    resp = gen.generate("SCN_001", {"raw_text": "农户小额贷款"}, "comprehensive")
    assert resp.script.scenario_id == "SCN_001"
    assert resp.script.scenario_name
    assert resp.script.content
    assert resp.script.script_type == "comprehensive"
    # mock mode: llm not used, fallback notice present
    assert resp.script.llm_used is False
    assert "AI生成" in resp.script.disclaimer or "人工复核" in resp.script.disclaimer
    assert "LLM" in resp.script.disclaimer or "未配置" in resp.script.disclaimer


def test_script_generation_nonexistent_scenario():
    gen = get_script_generator()
    resp = gen.generate("SCN_NONEXIST", {}, "marketing")
    assert "不存在" in resp.script.content
    assert resp.script.llm_used is False


def test_scenarios_api_endpoints():
    # GET /scenarios
    resp = client.get("/api/v1/scenarios")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 30

    # GET /scenarios?domain=credit_risk
    resp = client.get("/api/v1/scenarios?domain=credit_risk")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 10
    assert all(sc["domain"] == "credit_risk" for sc in data)

    # POST /scenarios/match
    resp = client.post(
        "/api/v1/scenarios/match",
        json={
            "parse_result": {
                "raw_text": "农户小额贷款贷前风控",
                "intent": "credit_risk",
            },
            "top_k": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_scenarios"] >= 30
    assert len(data["matches"]) == 3
    assert data["matches"][0]["scenario"]["scenario_id"] == "SCN_001"

    # POST /scenarios/{id}/generate-script
    resp = client.post(
        "/api/v1/scenarios/SCN_001/generate-script",
        json={
            "scenario_id": "SCN_001",
            "parse_result": {"raw_text": "农户小额贷款"},
            "script_type": "marketing",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["script"]["scenario_id"] == "SCN_001"
    assert data["script"]["content"]
    assert "人工复核" in data["script"]["disclaimer"]

    # 404 for nonexistent scenario
    resp = client.post(
        "/api/v1/scenarios/SCN_NONEXIST/generate-script",
        json={"scenario_id": "", "parse_result": {}, "script_type": "marketing"},
    )
    assert resp.status_code == 404
