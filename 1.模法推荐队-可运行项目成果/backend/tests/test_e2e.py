"""
End-to-end integration tests covering all three demo paths.
Tests the full flow: parse -> recommend -> composition -> report.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_recommendation_rejects_query_only_payload():
    """Do not silently rank an empty demand when the frontend contract drifts."""
    response = client.post(
        "/api/v1/recommend-models",
        json={"query": "县域新客首贷营销", "top_k": 5},
    )

    assert response.status_code == 422
    errors = response.json()["details"]["errors"]
    assert any(item["loc"][-1] == "parse_result" for item in errors)
    assert any(item["loc"][-1] == "query" for item in errors)


def test_explicit_demo_policy_does_not_report_official_recommendation_count():
    parse_resp = client.post(
        "/api/v1/parse-demand",
        json={"raw_text": "县域新客首贷营销"},
    )
    rec_resp = client.post(
        "/api/v1/recommend-models",
        json={
            "parse_result": parse_resp.json(),
            "model_source": "demo",
            "top_k": 2,
        },
    )

    assert rec_resp.status_code == 200
    data = rec_resp.json()
    assert data["catalog_policy"] == "demo"
    assert len(data["recommendations"]) == 2
    assert all(item["source"] == "demo" for item in data["recommendations"])
    assert data["official_recommendation_count"] == 0
    assert data["demo_references"] == []
    assert data["demo_reference_count"] == 0


class TestE2EMarketingPath:
    """E2E test for customer marketing path."""

    DEMAND_TEXT = "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。"

    def test_full_marketing_flow(self):
        """Complete flow: parse -> recommend -> model detail -> report."""
        # 1. Parse demand
        parse_resp = client.post("/api/v1/parse-demand", json={
            "raw_text": self.DEMAND_TEXT,
        })
        assert parse_resp.status_code == 200
        parse_data = parse_resp.json()
        assert parse_data["intent"] == "customer_marketing"

        # 2. Recommend models
        rec_resp = client.post("/api/v1/recommend-models", json={
            "parse_result": parse_data,
            "top_k": 3,
        })
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert len(rec_data["recommendations"]) >= 2
        assert rec_data["catalog_policy"] == "official_then_demo"
        assert rec_data["demo_reference_status"] == "available"
        assert all(item["source"] == "official" for item in rec_data["recommendations"])
        assert len(rec_data["demo_references"]) == 3
        assert all(item["source"] == "demo" for item in rec_data["demo_references"])

        # 3. Get model detail for top model
        top_model_id = rec_data["recommendations"][0]["model_id"]
        detail_resp = client.get(f"/api/v1/models/{top_model_id}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["model_id"] == top_model_id
        assert detail_data["input_schema"]["type"] == "object"
        assert detail_data["output_schema"]["type"] == "object"
        assert detail_data["result_schema"]["type"] == "object"
        assert detail_data["permission_scope"]
        assert detail_data["legal_boundary"]

        # 4. Generate report
        report_resp = client.post("/api/v1/reports/recommendation", json={
            "request_id": rec_data["request_id"],
            "format": "markdown",
            "parse_result": parse_data,
            "recommend_result": rec_data,
        })
        assert report_resp.status_code == 200
        report_data = report_resp.json()
        assert report_data["request_id"] == rec_data["request_id"]
        assert report_data["generation_source"] in {"rule", "llm", "fallback"}
        assert "县域新客首贷营销" in report_data["raw_content"]
        assert rec_data["recommendations"][0]["model_name"] in report_data["raw_content"]
        assert "Demo参考候选（非官方）" in report_data["raw_content"]
        assert len(report_data["sections"]) > 0

        # 5. Check evaluation metrics
        eval_resp = client.get("/api/v1/evaluation/metrics")
        assert eval_resp.status_code == 200
        eval_data = eval_resp.json()
        assert eval_data["total_models_covered"] > 0

    def test_marketing_composition(self):
        """Test composition flow for marketing."""
        parse_resp = client.post("/api/v1/parse-demand", json={
            "raw_text": self.DEMAND_TEXT,
        })
        comp_resp = client.post("/api/v1/recommend-composition", json={
            "parse_result": parse_resp.json(),
        })
        assert comp_resp.status_code == 200
        data = comp_resp.json()
        assert len(data["scenario"]) > 0


class TestE2ERiskPrePath:
    """E2E test for pre-loan risk control path."""

    DEMAND_TEXT = "帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。"

    def test_full_risk_pre_flow(self):
        """Complete flow: parse -> recommend -> composition -> model detail."""
        # 1. Parse
        parse_resp = client.post("/api/v1/parse-demand", json={
            "raw_text": self.DEMAND_TEXT,
        })
        assert parse_resp.status_code == 200
        parse_data = parse_resp.json()
        assert parse_data["domain"] == "信贷风控"

        # 2. Recommend
        rec_resp = client.post("/api/v1/recommend-models", json={
            "parse_result": parse_data,
        })
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()

        # 3. Composition
        comp_resp = client.post("/api/v1/recommend-composition", json={
            "parse_result": parse_data,
        })
        assert comp_resp.status_code == 200
        comp_data = comp_resp.json()
        assert len(comp_data["nodes"]) >= 2

        # 4. Model detail
        model_id = rec_data["recommendations"][0]["model_id"]
        detail_resp = client.get(f"/api/v1/models/{model_id}")
        assert detail_resp.status_code == 200
        detail_data = detail_resp.json()
        assert detail_data["model_id"] == model_id
        assert detail_data["input_schema"]["type"] == "object"
        assert detail_data["output_schema"]["type"] == "object"
        assert detail_data["permission_scope"]


class TestE2EPostLoanPath:
    """E2E test for post-loan early warning path."""

    DEMAND_TEXT = "我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。"

    def test_full_post_loan_flow(self):
        """Complete flow: parse -> recommend -> composition."""
        # 1. Parse
        parse_resp = client.post("/api/v1/parse-demand", json={
            "raw_text": self.DEMAND_TEXT,
        })
        assert parse_resp.status_code == 200
        parse_data = parse_resp.json()
        assert "贷后" in parse_data.get("business_stage", "")

        # 2. Recommend
        rec_resp = client.post("/api/v1/recommend-models", json={
            "parse_result": parse_data,
        })
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        model_ids = [r["model_id"] for r in rec_data["recommendations"]]
        # Verify at least one model is recommended
        assert len(rec_data["recommendations"]) > 0

        # 3. Composition
        comp_resp = client.post("/api/v1/recommend-composition", json={
            "parse_result": parse_data,
        })
        assert comp_resp.status_code == 200
        comp_data = comp_resp.json()
        assert "预警" in comp_data["scenario"]


class TestE2EModelNotFound:
    """Test model not found case."""

    def test_model_not_found(self):
        """GET /api/v1/models/nonexistent should return 404."""
        response = client.get("/api/v1/models/INVALID_ID")
        assert response.status_code == 404


class TestE2ERootAndDocs:
    """Test root and docs endpoints."""

    def test_root_endpoint(self):
        """GET / should return app info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["app"] == "model-market-assistant"

    def test_openapi_docs(self):
        """OpenAPI docs should be accessible."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_json(self):
        """OpenAPI JSON should be accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "model-market-assistant"
