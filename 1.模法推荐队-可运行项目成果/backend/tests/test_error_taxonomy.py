import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_error_taxonomy import build_taxonomy, classify_failure


class FakeRepository:
    def __init__(self):
        self.models = {
            "gold": {
                "domain": "credit_risk",
                "business_stage": ["post_loan"],
                "customer_segment": ["farmer"],
                "output_fields": ["risk_level"],
                "data_readiness_score": 40,
            },
            "wrong": {
                "domain": "customer_marketing",
                "business_stage": ["pre_marketing"],
                "customer_segment": ["corporate"],
                "output_fields": ["conversion_probability"],
            },
            "same": {
                "domain": "credit_risk",
                "business_stage": ["post_loan"],
                "customer_segment": ["farmer"],
                "output_fields": ["risk_score"],
            },
        }

    def get_model(self, model_id):
        return self.models.get(model_id)


def test_classifies_metadata_confusion_and_illegal_id():
    result = classify_failure(["wrong", "illegal"], "gold", repository=FakeRepository())
    assert set(result["categories"]) == {
        "llm_illegal_id",
        "domain_confusion",
        "stage_confusion",
        "segment_confusion",
        "output_confusion",
        "data_gap_misjudgment",
    }


def test_classifies_similar_model_confusion():
    result = classify_failure(["same"], "gold", repository=FakeRepository())
    assert "similar_model_confusion" in result["categories"]
    assert "domain_confusion" not in result["categories"]


def test_build_taxonomy_rejects_test_report(tmp_path):
    path = tmp_path / "test.json"
    path.write_text(
        json.dumps({"evaluation_metadata": {"split": "test"}, "topk_evaluation": {"split": "test"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="train/val only"):
        build_taxonomy([path], repository=FakeRepository())
