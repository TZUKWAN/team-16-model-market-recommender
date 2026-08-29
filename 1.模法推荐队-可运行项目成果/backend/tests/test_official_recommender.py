"""Tests for OfficialRecommender — official_60 model recommendation engine."""

import pytest
from app.services.official_recommender import OfficialRecommender


@pytest.fixture(scope="module")
def recommender():
    """Module-level fixture: instantiate once for all tests."""
    return OfficialRecommender()


class TestOfficialRecommender:
    """Test suite for OfficialRecommender."""

    def test_loads_60_official_models(self, recommender):
        """Verify that exactly 60 OFFICIAL models are loaded."""
        assert len(recommender.models) == 60
        assert len(recommender.list_model_ids()) == 60

    def test_all_ids_are_official_prefix(self, recommender):
        """Verify every model_id starts with OFFICIAL_."""
        for mid in recommender.list_model_ids():
            assert mid.startswith("OFFICIAL_"), f"Model ID {mid} does not start with OFFICIAL_"

    def test_no_legacy_model_ids(self, recommender):
        """Verify no model_id uses legacy prefixes (RISK_, MKT_, OPS_)."""
        for mid in recommender.list_model_ids():
            assert not mid.startswith("RISK_"), f"Model ID {mid} has legacy prefix RISK_"
            assert not mid.startswith("MKT_"), f"Model ID {mid} has legacy prefix MKT_"
            assert not mid.startswith("OPS_"), f"Model ID {mid} has legacy prefix OPS_"

    def test_recommend_returns_top5(self, recommender):
        """Verify recommend returns 5 results with correct structure for a banking query."""
        results = recommender.recommend("农户小额贷款准入", 5)
        assert len(results) == 5
        for r in results:
            assert "model_id" in r
            assert "model_name" in r
            assert "score" in r
            assert "matched_keywords" in r
            assert "source_type" in r
            assert isinstance(r["score"], float)
            assert 0.0 <= r["score"] <= 100.0
            assert r["source_type"] == "official_dataset"

    def test_recommend_scores_are_sorted(self, recommender):
        """Verify scores are in descending order (allow equal values)."""
        results = recommender.recommend("农户小额贷款准入", 5)
        scores = [r["score"] for r in results]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Scores not descending: {scores}"

    def test_recommend_only_official_models(self, recommender):
        """Verify multiple queries all return OFFICIAL_* model IDs only."""
        queries = [
            "农户小额贷款准入",
            "小微企业违约预测",
            "反洗钱可疑交易监测",
            "对公贷款贷后预警",
            "信用卡逾期催收模型",
        ]
        for query in queries:
            results = recommender.recommend(query, 5)
            for r in results:
                assert r["model_id"].startswith("OFFICIAL_"), (
                    f"Query {query!r} returned non-OFFICIAL model: {r['model_id']}"
                )

    def test_empty_query_fallback(self, recommender):
        """Verify empty query returns 5 results (all score 0, sorted by model_id)."""
        results = recommender.recommend("", 5)
        assert len(results) == 5
        # All scores should be 0.0 for empty query
        for r in results:
            assert r["score"] == 0.0

    def test_get_model_by_id(self, recommender):
        """Verify get_model_by_id returns correct model for valid ID and None for invalid."""
        model = recommender.get_model_by_id("OFFICIAL_001")
        assert model is not None
        assert isinstance(model, dict)
        assert model["model_id"] == "OFFICIAL_001"

        none_result = recommender.get_model_by_id("FAKE_999")
        assert none_result is None
