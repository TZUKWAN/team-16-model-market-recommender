from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.composition import RecommendCompositionRequest
from app.schemas.recommendation import RecommendModelsRequest
from app.services.hybrid_retriever import DenseRetrievalUnavailableError
from app.services.composition_planner import CompositionPlanner
from app.services.data_loader import load_models
from app.services.recommender import (
    ModelCatalogUnavailableError,
    ModelRecommendationService,
)


def service_with(models: list[dict[str, str]]) -> ModelRecommendationService:
    service = object.__new__(ModelRecommendationService)
    service.models = models
    return service


def test_request_defaults_to_official_then_demo_policy() -> None:
    request = RecommendModelsRequest(parse_result={"raw_text": "贷款准入"})
    assert request.model_source == "official_then_demo"
    assert request.demo_top_k == 3


def test_request_rejects_mixed_or_unknown_catalog() -> None:
    with pytest.raises(ValidationError):
        RecommendModelsRequest(parse_result={}, model_source="mixed")


def test_request_accepts_explicit_single_catalog_policies() -> None:
    assert RecommendModelsRequest(parse_result={}, model_source="official").model_source == "official"
    assert RecommendModelsRequest(parse_result={}, model_source="demo").model_source == "demo"


def test_composition_request_defaults_to_official_and_rejects_mixed() -> None:
    request = RecommendCompositionRequest(parse_result={"raw_text": "贷款准入"})
    assert request.model_source == "official"
    with pytest.raises(ValidationError):
        RecommendCompositionRequest(parse_result={}, model_source="mixed")


def test_model_pool_defaults_to_official_and_demo_is_explicit() -> None:
    service = service_with(
        [
            {"model_id": "OFFICIAL_001", "source": "official"},
            {"model_id": "MKT_001", "source": "demo"},
        ]
    )
    assert [row["model_id"] for row in service._model_pool({})] == ["OFFICIAL_001"]
    assert [row["model_id"] for row in service._model_pool({"model_source": "demo"})] == [
        "MKT_001"
    ]


def test_requested_catalog_never_falls_back_to_other_source() -> None:
    service = service_with([{"model_id": "MKT_001", "source": "demo"}])
    with pytest.raises(ModelCatalogUnavailableError) as exc_info:
        service._model_pool({"model_source": "official"})
    assert exc_info.value.source == "official"


def test_composition_pool_uses_one_explicit_catalog_without_fallback() -> None:
    planner = object.__new__(CompositionPlanner)
    planner.models = [
        {"model_id": "OFFICIAL_001", "source": "official"},
        {"model_id": "MKT_001", "source": "demo"},
    ]
    assert [row["model_id"] for row in planner._model_pool({})] == ["OFFICIAL_001"]
    assert [row["model_id"] for row in planner._model_pool({"model_source": "demo"})] == [
        "MKT_001"
    ]

    planner.models = [{"model_id": "MKT_001", "source": "demo"}]
    with pytest.raises(ModelCatalogUnavailableError):
        planner._model_pool({"model_source": "official"})


def test_integrated_catalog_has_expected_source_counts() -> None:
    models = load_models()
    official = [row for row in models if row.get("source") == "official"]
    demo = [row for row in models if row.get("source") == "demo"]
    assert len(official) == 60
    assert len(demo) == 105
    assert {row.get("catalog_version") for row in official} == {"official-v1"}
    assert {row.get("catalog_version") for row in demo} == {"demo-v1"}


def test_default_policy_returns_separate_official_and_demo_sections() -> None:
    service = ModelRecommendationService()
    result = service.recommend(
        {
            "raw_text": "县域新客首贷营销",
            "intent": "customer_marketing",
            "business_scenario": "县域新客首贷营销",
            "model_source": "official_then_demo",
        },
        top_k=5,
        demo_top_k=3,
        use_llm=False,
        use_llm_reason=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=False,
    )

    assert result.catalog_policy == "official_then_demo"
    assert result.demo_reference_status == "available"
    assert result.official_recommendation_count == 5
    assert result.demo_reference_count == 3
    assert len(result.recommendations) == 5
    assert len(result.demo_references) == 3
    assert {item.source for item in result.recommendations} == {"official"}
    assert {item.source for item in result.demo_references} == {"demo"}
    assert all(item.model_id.startswith("OFFICIAL_") for item in result.recommendations)
    assert all(not item.model_id.startswith("OFFICIAL_") for item in result.demo_references)


def test_missing_demo_catalog_does_not_replace_official_ranking() -> None:
    service = ModelRecommendationService()
    service.models = [row for row in service.models if row.get("source") == "official"]
    result = service.recommend(
        {
            "raw_text": "贷款准入",
            "intent": "credit_risk",
            "model_source": "official_then_demo",
        },
        top_k=2,
        demo_top_k=2,
        use_llm=False,
        use_llm_reason=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=False,
    )

    assert len(result.recommendations) == 2
    assert {item.source for item in result.recommendations} == {"official"}
    assert result.demo_references == []
    assert result.demo_reference_status == "unavailable"
    assert "未回退" in result.summary


def test_api_returns_503_when_required_dense_runtime_is_unavailable(client, monkeypatch) -> None:
    from app.api.v1 import recommend_models as recommend_api

    class DenseUnavailableService:
        @staticmethod
        def recommend(**_kwargs):
            raise DenseRetrievalUnavailableError(
                {
                    "retrieval_runtime_mode": "competition_dense",
                    "dense_error_code": "DENSE_ARTIFACT_MISSING",
                }
            )

    monkeypatch.setattr(
        recommend_api,
        "get_model_recommendation_service",
        lambda: DenseUnavailableService(),
    )

    response = client.post(
        "/api/v1/recommend-models",
        json={"parse_result": {"raw_text": "贷款准入"}},
    )

    assert response.status_code == 503
    assert response.json()["code"] == "DENSE_RETRIEVAL_UNAVAILABLE"
    assert response.json()["details"]["dense_error_code"] == "DENSE_ARTIFACT_MISSING"


def test_api_recommendation_does_not_come_from_frontend_mock() -> None:
    """Prove page recommendations are backend-computed, not recommendMock.ts data.

    The frontend mock fixture (frontend/src/mocks/recommendMock.ts) is only used
    when VITE_USE_MOCK=true or as an explicit fallback. The official top-1 for
    the canonical marketing demand must be an OFFICIAL_* model that appears
    nowhere in the mock fixture file.
    """
    from pathlib import Path
    import re

    mock_path = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "mocks" / "recommendMock.ts"
    )
    mock_text = mock_path.read_text(encoding="utf-8")
    mock_ids = set(re.findall(r"model_id:\s*'([^']+)'", mock_text))
    assert mock_ids, "mock fixture must contain model ids for this guard to be meaningful"

    service = ModelRecommendationService()
    result = service.recommend(
        {
            "raw_text": "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。",
            "intent": "customer_marketing",
            "business_scenario": "县域新客首贷营销",
            "model_source": "official_then_demo",
        },
        top_k=5,
        demo_top_k=3,
        use_llm=False,
        use_llm_reason=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=False,
    )

    top = result.recommendations[0]
    assert top.model_id.startswith("OFFICIAL_")
    assert top.model_id not in mock_ids
    assert all(item.model_id not in mock_ids for item in result.recommendations)
