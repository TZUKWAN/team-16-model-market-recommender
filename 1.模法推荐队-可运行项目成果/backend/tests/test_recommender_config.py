"""Tests for recommendation weights configuration."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.recommender import ModelRecommendationService


class TestWeightsConfig:
    """C-TASK-4: Recommendation weights loaded from config."""

    def test_service_initializes_with_weights(self):
        """Service should initialize and load weights."""
        service = ModelRecommendationService()
        assert service.rec_weights is not None
        assert isinstance(service.rec_weights, dict)

    def test_weights_contain_all_dimensions(self):
        """All 7 scoring dimensions should be present."""
        service = ModelRecommendationService()
        expected_keys = {
            "scenario", "customer", "data", "output",
            "performance", "landing", "compliance",
        }
        assert expected_keys.issubset(service.rec_weights.keys())

    def test_weights_sum_to_one(self):
        """Weights should sum to approximately 1.0 (allowing tiny float error)."""
        service = ModelRecommendationService()
        total = sum(service.rec_weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected ~1.0"

    def test_weights_are_positive(self):
        """All individual weights should be greater than 0."""
        service = ModelRecommendationService()
        for key, val in service.rec_weights.items():
            assert val > 0, f"Weight '{key}' is {val}, expected > 0"

    def test_recommend_works_with_config_weights(self):
        """Recommend API should produce valid results using config-loaded weights."""
        service = ModelRecommendationService()
        parse_result = {
            "intent": "credit_risk",
            "tags": ["farmer"],
            "business_scenario": "农户小额贷款贷前准入",
        }
        result = service.recommend(parse_result, top_k=3)
        assert len(result.recommendations) > 0
        assert result.recommendations[0].total_score > 0

    def test_weighted_scoring_uses_rec_weights(self):
        """Score calculation should reference rec_weights from the service."""
        service = ModelRecommendationService()
        model = service.models[0]
        parse_result = {
            "intent": "customer_marketing",
            "tags": ["county_new_customer"],
            "business_scenario": "县域新客首贷营销",
            "customer_segment": ["县域新客"],
            "expected_outputs": ["转化概率"],
        }
        score, breakdown = service._score(model, parse_result)
        assert score > 0
        assert breakdown is not None

    def test_fallback_on_missing_config(self):
        """Service should fall back to module-level defaults when config is missing."""
        fake_path = Path(__file__).resolve().parent / "fixtures" / "__missing__.json"

        with patch.object(
            ModelRecommendationService, '_recommendation_weights_path',
            return_value=fake_path
        ):
            fallback_service = ModelRecommendationService()
            assert fallback_service.rec_weights is not None
            from app.services.recommender import (
                W_SCENARIO, W_CUSTOMER, W_DATA, W_OUTPUT,
                W_PERFORMANCE, W_LANDING, W_COMPLIANCE,
            )
            assert fallback_service.rec_weights["scenario"] == W_SCENARIO
            assert fallback_service.rec_weights["customer"] == W_CUSTOMER
            assert fallback_service.rec_weights["data"] == W_DATA
            assert fallback_service.rec_weights["output"] == W_OUTPUT
            assert fallback_service.rec_weights["performance"] == W_PERFORMANCE
            assert fallback_service.rec_weights["landing"] == W_LANDING
            assert fallback_service.rec_weights["compliance"] == W_COMPLIANCE

    def test_recommend_still_works_with_fallback(self):
        """Recommend should work even when falling back to default weights."""
        fake_path = Path(__file__).resolve().parent / "fixtures" / "__missing__.json"

        with patch.object(
            ModelRecommendationService, '_recommendation_weights_path',
            return_value=fake_path
        ):
            fallback_service = ModelRecommendationService()
            result = fallback_service.recommend(
                {"intent": "customer_marketing", "tags": ["marketing"]},
                top_k=1,
            )
            assert len(result.recommendations) > 0

    def test_config_file_loaded_when_exists(self):
        """Service should load and normalize weights from an existing config file."""
        real_fixture = Path(__file__).resolve().parent / "fixtures" / "recommendation_weights_test.json"

        with patch.object(
            ModelRecommendationService, '_recommendation_weights_path',
            return_value=real_fixture
        ):
            service = ModelRecommendationService()
            assert service.rec_weights is not None
            assert abs(sum(service.rec_weights.values()) - 1.0) < 0.01
            for v in service.rec_weights.values():
                assert v > 0

    def test_dense_retrieval_environment_overrides_are_applied(self, monkeypatch):
        monkeypatch.setenv("HYBRID_DENSE_ENABLED", "true")
        monkeypatch.setenv("HYBRID_DENSE_WEIGHT", "0.35")
        monkeypatch.setenv("HYBRID_DENSE_MODEL", "local/test-embedding")

        service = ModelRecommendationService()

        assert service.hybrid_config["dense_enabled"] is True
        assert service.hybrid_config["dense_weight"] == pytest.approx(0.35)
        assert service.hybrid_config["dense_model"] == "local/test-embedding"
        assert Path(service.hybrid_config["dense_cache_dir"]).is_absolute()

    def test_competition_dense_mode_is_required_offline_and_manifest_verified(
        self, monkeypatch, tmp_path
    ):
        manifest_path = tmp_path / "bge-m3.manifest.json"
        monkeypatch.setenv("RETRIEVAL_RUNTIME_MODE", "competition_dense")
        monkeypatch.setenv("HYBRID_DENSE_ENABLED", "true")
        monkeypatch.setenv("HYBRID_DENSE_WEIGHT", "0.5")
        monkeypatch.setenv("HYBRID_DENSE_MODEL", str(tmp_path / "bge-m3"))
        monkeypatch.setenv("HYBRID_DENSE_MANIFEST", str(manifest_path))
        monkeypatch.setenv("HYBRID_DENSE_EXPECTED_REVISION", "a" * 40)

        service = ModelRecommendationService()

        assert service.hybrid_config["runtime_mode"] == "competition_dense"
        assert service.hybrid_config["dense_required"] is True
        assert service.hybrid_config["dense_offline"] is True
        assert service.hybrid_config["dense_verify_manifest"] is True
        assert service.hybrid_config["dense_expected_dimension"] == 1024
        assert service.hybrid_config["dense_expected_revision"] == "a" * 40
