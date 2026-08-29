"""Tests for the health check endpoint."""

from fastapi.testclient import TestClient
from app.main import app
from app.api.v1 import health as health_module

client = TestClient(app)


class TestHealth:
    """Health endpoint test suite."""

    def test_health_returns_200(self):
        """GET /api/v1/health should return 200."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_response_structure(self):
        """Health response should contain expected fields."""
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert data["app_name"] == "model-market-assistant"
        assert "timestamp" in data
        assert "official_dataset_loaded" in data
        assert "llm_enabled" in data
        assert "llm_provider" in data
        assert "model_market_connected" in data
        assert "demo_result_mode" in data
        assert data["model_asset_repository_ready"] is True
        assert data["model_asset_total"] >= 165
        assert data["model_asset_by_source"]["demo"] >= 105
        assert data["model_asset_by_source"]["official"] >= 60
        assert data["model_asset_validation_issues"] == 0
        assert data["retrieval_runtime_mode"] == "light"
        assert data["dense_required"] is False
        assert data["dense_runtime_ready"] is True

    def test_required_dense_runtime_marks_health_degraded(self, monkeypatch):
        class DenseUnavailableService:
            @staticmethod
            def dense_runtime_status():
                return {
                    "retrieval_runtime_mode": "competition_dense",
                    "dense_requested": True,
                    "dense_required": True,
                    "dense_initialized": True,
                    "dense_available": False,
                    "dense_model": "/app/models/bge-m3",
                    "dense_weight": 0.5,
                    "dense_embedding_dimension": 0,
                    "dense_expected_dimension": 1024,
                    "dense_offline": True,
                    "dense_manifest_required": True,
                    "dense_manifest_verified": False,
                    "dense_cache_enabled": True,
                    "dense_cache_ready": False,
                    "dense_cache_hit": False,
                    "dense_error_code": "DENSE_ARTIFACT_MISSING",
                    "dense_config_error": "",
                    "dense_checked_at": "2026-07-15T00:00:00Z",
                }

        monkeypatch.setattr(
            health_module,
            "get_model_recommendation_service",
            lambda: DenseUnavailableService(),
        )

        response = client.get("/api/v1/health")
        data = response.json()

        assert response.status_code == 200
        assert data["status"] == "degraded"
        assert data["dense_runtime_ready"] is False
        assert data["dense_error_code"] == "DENSE_ARTIFACT_MISSING"
