import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from summarize_hybrid_calibration import select_val_result, validate_train_pairs


def test_select_val_result_rejects_test_report(tmp_path):
    path = tmp_path / "test.json"
    path.write_text(
        json.dumps({"evaluation_metadata": {"split": "test"}, "topk_evaluation": {"split": "test"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="val reports only"):
        select_val_result([path])


def test_select_val_result_prefers_top3_then_top5(tmp_path):
    paths = []
    for weight, top3, top5 in ((0.2, 89.0, 96.0), (0.5, 91.0, 95.0)):
        path = tmp_path / f"w{weight}.json"
        path.write_text(
            json.dumps(
                {
                    "evaluation_metadata": {"split": "val", "dense_weight_override": weight},
                    "topk_evaluation": {
                        "split": "val",
                        "top3_hit_rate_pct": top3,
                        "top5_hit_rate_pct": top5,
                        "macro_by_gold_model_top3_pct": top3,
                        "macro_by_gold_model_top5_pct": top5,
                        "retrieval_evidence": {"dense_case_coverage_pct": 100.0},
                    },
                }
            ),
            encoding="utf-8",
        )
        paths.append(path)
    selected, _ = select_val_result(paths)
    assert selected["weight"] == 0.5
