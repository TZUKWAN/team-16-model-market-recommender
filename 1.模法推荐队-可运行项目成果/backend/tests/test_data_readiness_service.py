"""Tests for data readiness diagnostics."""

from app.services.data_readiness_service import DataReadinessService
from app.services.recommender import ModelRecommendationService


def test_data_readiness_detects_missing_required_fields():
    service = DataReadinessService()
    model = {
        "input_fields_required": ["credit_report", "transaction_flow"],
        "input_fields_optional": ["customer_profile"],
        "model_capability": ["admission_scoring"],
    }
    parse_result = {"data_conditions": ["customer_profile"]}

    report = service.diagnose(model, parse_result)

    assert report.readiness_score < 50
    assert "credit_report" in report.missing_required_fields
    assert "transaction_flow" in report.missing_required_fields
    assert report.action_items
    assert report.substitution_notes


def test_data_readiness_marks_complete_data_as_low_impact():
    service = DataReadinessService()
    model = {
        "input_fields_required": ["credit_report", "transaction_flow"],
        "input_fields_optional": [],
    }
    parse_result = {"data_conditions": ["credit_report", "transaction_flow"]}

    report = service.diagnose(model, parse_result)

    assert report.readiness_score == 100
    assert report.missing_required_fields == []
    assert "接入验证" in report.confidence_impact


def test_recommendations_include_data_readiness_report():
    recommender = ModelRecommendationService()
    result = recommender.recommend({
        "intent": "credit_risk",
        "business_scenario": "农户小额贷款贷前准入",
        "tags": ["credit_risk", "farmer", "admission_scoring"],
        "data_conditions": ["customer_profile"],
    }, top_k=1)

    assert result.recommendations
    readiness = result.recommendations[0].data_readiness
    assert readiness.required_fields
    assert readiness.confidence_impact
