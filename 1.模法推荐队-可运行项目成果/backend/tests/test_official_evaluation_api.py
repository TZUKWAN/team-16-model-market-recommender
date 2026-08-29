"""
Tests for the Official Evaluation API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

BASE = "/api/v1/official-evaluation"


class TestOfficialEvaluationSummary:
    def test_summary_ok(self):
        resp = client.get(f"{BASE}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "top1_accuracy" in data
        assert "top3_accuracy" in data
        assert "top5_accuracy" in data

    def test_summary_404_when_missing(self, monkeypatch):
        import app.api.v1.official_evaluation as mod

        monkeypatch.setattr(mod, "REPORTS_DIR", mod._PROJECT_ROOT / "reports" / "nonexistent")
        resp = client.get(f"{BASE}/summary")
        assert resp.status_code == 404
        body = resp.json()
        # Global error handler wraps detail into message
        assert "not found" in body.get("message", body.get("detail", "")).lower()


class TestOfficialEvaluationResults:
    @pytest.mark.parametrize("split", ["val", "test"])
    def test_results_ok(self, split):
        resp = client.get(f"{BASE}/results", params={"split": split})
        assert resp.status_code == 200
        data = resp.json()
        assert data["split"] == split

    def test_results_invalid_split(self):
        resp = client.get(f"{BASE}/results", params={"split": "invalid"})
        assert resp.status_code == 422

    def test_results_missing_split(self):
        resp = client.get(f"{BASE}/results")
        assert resp.status_code == 422


class TestOfficialEvaluationFailures:
    def test_failures_ok(self):
        resp = client.get(f"{BASE}/failures")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_failures_filter_split(self):
        resp = client.get(f"{BASE}/failures", params={"split": "test"})
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["split"] == "test"

    def test_failures_filter_type(self):
        resp = client.get(f"{BASE}/failures", params={"failure_type": "keyword_missing"})
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["failure_type"] == "keyword_missing"

    def test_failures_filter_both(self):
        resp = client.get(
            f"{BASE}/failures",
            params={"split": "test", "failure_type": "keyword_missing"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for f in data:
            assert f["split"] == "test"
            assert f["failure_type"] == "keyword_missing"


class TestOfficialEvaluationDataset:
    def test_dataset_ok(self):
        resp = client.get(f"{BASE}/dataset")
        assert resp.status_code == 200
        data = resp.json()
        assert "manifest" in data
        assert "model_count" in data
        assert data["model_count"] == 60
        assert "query_count" in data
        assert data["query_count"] == 417
        assert "splits" in data
        assert data["splits"]["train"] == 291
        assert data["splits"]["val"] == 64
        assert data["splits"]["test"] == 62

    def test_dataset_splits_include_train_test_val(self):
        resp = client.get(f"{BASE}/dataset")
        assert resp.status_code == 200
        data = resp.json()
        assert "splits" in data
        assert data["splits"]["train"] == 291
        assert data["splits"]["test"] == 62
        assert data["splits"]["val"] == 64
        assert data["model_count"] == 60
        assert data["query_count"] == 417
