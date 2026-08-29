"""Regression tests for enriched official model catalog dimensions."""

import json
from pathlib import Path

from app.services.data_loader import _adapt_official_model, load_official_models

CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "official" / "model_catalog_structured.jsonl"


def _read_catalog_records() -> list[dict]:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_official_catalog_enrichment_fields_are_complete():
    records = _read_catalog_records()

    assert len(records) == 60
    assert not [r["model_id"] for r in records if not r.get("customer_segment")]
    assert not [r["model_id"] for r in records if not r.get("performance_metrics")]
    assert not [r["model_id"] for r in records if not r.get("historical_cases")]
    assert all(isinstance(r["customer_segment"], list) for r in records)
    assert all(isinstance(r["performance_metrics"], dict) for r in records)
    assert all(isinstance(r["historical_cases"], list) for r in records)
    assert all(r.get("enrichment_review_status") == "draft_requires_manual_review" for r in records)
    assert all(r.get("enrichment_method") == "deterministic_local_rules_no_external_llm" for r in records)


def test_official_adapter_preserves_enriched_dimensions():
    records = load_official_models()
    record = next(r for r in records if r.get("model_id") == "OFFICIAL_001")

    adapted = _adapt_official_model(record)

    assert adapted["customer_segment"] == record["customer_segment"]
    assert adapted["performance_metrics"] == record["performance_metrics"]
    assert adapted["historical_cases"] == record["historical_cases"]


def test_model_metadata_accepts_metric_note():
    """ModelMetadata schema must accept string-valued metric_note in performance_metrics."""
    from app.schemas.model import ModelMetadata
    records = load_official_models()
    record = next(r for r in records if r.get("model_id") == "OFFICIAL_001")
    adapted = _adapt_official_model(record)
    # Must not raise ValidationError even though metric_note is a string
    metadata = ModelMetadata(**adapted)
    assert "metric_note" in metadata.performance_metrics
    assert isinstance(metadata.performance_metrics["metric_note"], str)
    assert metadata.performance_metrics["metric_note"]
