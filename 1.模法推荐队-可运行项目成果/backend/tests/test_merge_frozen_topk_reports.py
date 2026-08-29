import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from merge_frozen_topk_reports import merge_topk_reports


def _report(split, total, top3, top5):
    return {
        "evaluation_metadata": {"split": split, "dense_weight_override": 0.5},
        "topk_evaluation": {
            "split": split,
            "total": total,
            "top3_hits": top3,
            "top5_hits": top5,
            "per_gold_model": {
                "m1": {"total": total, "top3_hits": top3, "top5_hits": top5}
            },
            "per_scenario": {
                "risk": {"total": total, "top3_hits": top3, "top5_hits": top5}
            },
            "llm_evidence": {"parser_fallback_count": 0},
            "retrieval_evidence": {"dense_available_case_count": total},
            "details": [{"test_id": f"{split}_1"}],
        },
    }


def test_merge_topk_reports_recomputes_counts():
    merged = merge_topk_reports(
        {
            "train": _report("train", 2, 1, 2),
            "val": _report("val", 1, 1, 1),
            "test": _report("test", 1, 1, 1),
        }
    )
    assert merged["total"] == 4
    assert merged["top3_hit_rate_pct"] == 75.0
    assert merged["top5_hit_rate_pct"] == 100.0
    assert merged["retrieval_evidence"]["dense_available_case_count"] == 4
    assert len(merged["details"]) == 3


def test_merge_rejects_wrong_split():
    reports = {
        "train": _report("train", 1, 1, 1),
        "val": _report("test", 1, 1, 1),
        "test": _report("test", 1, 1, 1),
    }
    with pytest.raises(ValueError, match="split mismatch"):
        merge_topk_reports(reports)
