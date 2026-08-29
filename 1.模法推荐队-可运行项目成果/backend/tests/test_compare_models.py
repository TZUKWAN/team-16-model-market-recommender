"""Tests for model comparison and effect estimates."""


def test_compare_models_endpoint_returns_matrix_and_estimates(client):
    payload = {
        "model_ids": ["OFFICIAL_001", "OFFICIAL_002"],
        "parse_result": {
            "intent": "customer_marketing",
            "business_scenario": "中高端客户维稳增存",
            "customer_segment": ["中高端客户"],
            "data_conditions": ["customer_profile", "transaction_history", "asset_liability"],
        },
    }

    response = client.post("/api/v1/compare-models", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"].startswith("cmp-")
    assert len(data["items"]) == 2
    assert data["matrix"]
    first = data["items"][0]
    assert first["effect_estimate"]["estimated_lift_pct"] >= 0
    assert first["effect_estimate"]["confidence_band_pct"]
    assert "非真实" in first["effect_estimate"]["disclaimer"]
    assert any(row["dimension"] == "数据就绪度" for row in data["matrix"])


def test_effect_estimate_has_evidence_level_and_source(client):
    """F1.1: Every effect estimate must carry metric_source, evidence_level, and not_for_decision."""
    payload = {
        "model_ids": ["OFFICIAL_001", "OFFICIAL_002"],
        "parse_result": {
            "intent": "customer_marketing",
            "business_scenario": "中高端客户维稳增存",
            "customer_segment": ["中高端客户"],
        },
    }
    response = client.post("/api/v1/compare-models", json=payload)
    assert response.status_code == 200
    for item in response.json()["items"]:
        est = item["effect_estimate"]
        assert est["metric_source"] in ("verified", "draft", "missing")
        assert est["evidence_level"] in ("high", "medium", "low")
        assert isinstance(est["not_for_decision"], bool)
        assert len(est["verification_status"]) > 0
        assert isinstance(est["assumptions"], list)
        assert len(est["assumptions"]) >= 2


def test_effect_estimate_low_readiness_suppresses_high_lift():
    """F1.1: Estimates must carry evidence fields and assumptions regardless of readiness."""
    from app.services.effect_estimator import EffectEstimator

    estimator = EffectEstimator()
    model = {
        "model_id": "TEST_001",
        "performance_metrics": {"auc": 0.85, "ks": 0.65},
        "source": "demo",
        "customer_segment": ["new_customer"],
        "required_data": ["customer_profile", "transaction_history"],
        "output_fields": ["score"],
    }
    parse_result = {"customer_segment": ["new_customer"]}
    result = estimator.estimate_effect(model, parse_result)
    assert result.metric_source in ("verified", "draft", "missing")
    assert result.evidence_level in ("high", "medium", "low")
    assert len(result.assumptions) >= 2
    assert isinstance(result.not_for_decision, bool)
    assert len(result.verification_status) > 0


def test_effect_estimate_missing_metrics_uses_conservative_default():
    """F1.1: Models without performance metrics must use 'missing' source and low evidence."""
    from app.services.effect_estimator import EffectEstimator

    estimator = EffectEstimator()
    model = {
        "model_id": "TEST_NOMETRIC",
        "performance_metrics": {},
        "source": "official",
        "customer_segment": [],
        "required_data": [],
        "output_fields": [],
    }
    parse_result = {"customer_segment": []}
    result = estimator.estimate_effect(model, parse_result)
    assert result.metric_source == "missing"
    assert result.evidence_level == "low"
    assert result.not_for_decision is True
    assert result.estimated_lift_pct <= 10.0