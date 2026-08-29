"""Tests for factual model-card hybrid retrieval and recommendation fusion."""

import hashlib
import json

import numpy as np

import pytest

from app.services.hybrid_retriever import (
    DenseRetrievalUnavailableError,
    HybridModelRetriever,
)
from app.services.recommender import ModelRecommendationService


MODELS = [
    {
        "model_id": "A",
        "model_name": "贷记卡账单分期营销模型",
        "description": "预测信用卡客户办理账单分期的概率",
        "business_scenario": ["账单分期精准营销"],
        "model_capability": ["conversion_prediction"],
        "output_fields": ["installment_probability"],
    },
    {
        "model_id": "B",
        "model_name": "企业贷款违约预警模型",
        "description": "识别对公贷款客户的逾期违约风险",
        "business_scenario": ["贷后风险预警"],
        "model_capability": ["default_prediction"],
        "output_fields": ["risk_score"],
    },
]


class FakeDenseEncoder:
    def __init__(self):
        self.calls = 0

    def encode(self, texts, normalize_embeddings=True):
        self.calls += 1
        vectors = []
        for text in texts:
            if "账单分期" in text:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return np.asarray(vectors)


def test_sparse_model_card_retrieval_prefers_relevant_model():
    retriever = HybridModelRetriever()

    scores = retriever.score("预测信用卡客户办理账单分期的概率", MODELS)

    assert scores["A"].retrieval_score > scores["B"].retrieval_score
    assert scores["A"].sparse_title > 0
    assert retriever.last_audit["mode"] == "sparse"
    assert retriever.last_audit["dense_available"] is False


def test_optional_dense_encoder_is_audited_and_fused():
    retriever = HybridModelRetriever(
        dense_enabled=True,
        dense_weight=0.5,
        dense_encoder=FakeDenseEncoder(),
    )

    scores = retriever.score("账单分期", MODELS)

    assert scores["A"].dense_score == 1.0
    assert scores["A"].retrieval_score > scores["B"].retrieval_score
    assert retriever.last_audit["mode"] == "sparse+dense"
    assert retriever.last_audit["dense_available"] is True


def test_dense_model_index_is_reused_from_validated_disk_cache(tmp_path):
    first_encoder = FakeDenseEncoder()
    first = HybridModelRetriever(
        dense_enabled=True,
        dense_weight=0.5,
        dense_encoder=first_encoder,
        dense_cache_dir=tmp_path,
    )
    first.score("账单分期", MODELS)
    assert first.last_audit["dense_index_cache_hit"] is False
    assert first_encoder.calls == 2  # model cards, then query

    second_encoder = FakeDenseEncoder()
    second = HybridModelRetriever(
        dense_enabled=True,
        dense_weight=0.5,
        dense_encoder=second_encoder,
        dense_cache_dir=tmp_path,
    )
    second.score("账单分期", MODELS)

    assert second.last_audit["dense_index_cache_hit"] is True
    assert second_encoder.calls == 1  # query only; model-card vectors came from cache


def test_competition_dense_mode_rejects_sparse_fallback():
    retriever = HybridModelRetriever(
        dense_enabled=True,
        dense_weight=0.5,
        dense_required=True,
        runtime_mode="competition_dense",
    )
    retriever._dense_load_attempted = True

    with pytest.raises(DenseRetrievalUnavailableError) as exc_info:
        retriever.score("账单分期", MODELS)

    assert exc_info.value.status["dense_required"] is True
    assert exc_info.value.status["dense_available"] is False
    assert exc_info.value.status["retrieval_runtime_mode"] == "competition_dense"


def test_competition_dense_mode_validates_embedding_dimension():
    retriever = HybridModelRetriever(
        dense_enabled=True,
        dense_weight=0.5,
        dense_encoder=FakeDenseEncoder(),
        dense_required=True,
        runtime_mode="competition_dense",
        dense_expected_dimension=1024,
    )

    with pytest.raises(DenseRetrievalUnavailableError) as exc_info:
        retriever.score("账单分期", MODELS)

    assert exc_info.value.status["dense_available"] is False
    assert exc_info.value.status["dense_embedding_dimension"] == 0
    assert exc_info.value.status["dense_error_code"] == "VALUEERROR"


def test_dense_manifest_rejects_unexpected_revision(tmp_path):
    model_dir = tmp_path / "bge-m3"
    model_dir.mkdir()
    artifact = model_dir / "config.json"
    artifact.write_text('{"hidden_size": 1024}', encoding="utf-8")
    manifest = tmp_path / "bge-m3.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "resolved_revision": "b" * 40,
                "embedding_dimension": 1024,
                "files": [
                    {
                        "path": "config.json",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retriever = HybridModelRetriever(
        dense_enabled=True,
        dense_weight=0.5,
        dense_model=str(model_dir),
        dense_expected_dimension=1024,
        dense_expected_revision="a" * 40,
        dense_manifest_path=manifest,
        dense_verify_manifest=True,
    )

    assert retriever._verify_dense_manifest() is False
    assert retriever.runtime_status()["dense_error_code"] == "MANIFEST_VALUEERROR"


def test_recommender_exposes_sparse_hybrid_score_without_keyword_rules(monkeypatch):
    monkeypatch.setenv("HYBRID_DENSE_ENABLED", "false")
    monkeypatch.setenv("HYBRID_DENSE_WEIGHT", "0")
    service = ModelRecommendationService()
    parse_result = {
        "raw_text": "信用卡客户出账单后，预测办理账单分期的概率",
        "intent": "customer_marketing",
        "business_scenario": "账单分期精准营销",
        "tags": ["customer_marketing", "credit_card", "conversion_prediction"],
        "expected_outputs": ["conversion_probability"],
        "model_source": "official",
    }

    result = service.recommend(
        parse_result,
        top_k=3,
        use_llm=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=True,
    )

    assert result.recommendations
    assert result.recommendations[0].retrieval_score > 0
    assert result.recommendations[0].score_breakdown.hybrid_retrieval_match > 0
    assert service.last_hybrid_retrieval_audit["enabled"] is True
    assert service.last_hybrid_retrieval_audit["mode"] == "sparse"
