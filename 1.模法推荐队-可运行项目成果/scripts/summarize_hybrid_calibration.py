"""Validate train-only hard negatives and select a dense weight on val only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_DIR = ROOT / "reports" / "calibration"
TRAIN_PAIRS = ROOT / "data" / "training" / "hard_negative_pairs.jsonl"
TRAIN_METADATA = ROOT / "data" / "training" / "hard_negative_pairs.metadata.json"
W05_PAIRS = CALIBRATION_DIR / "hard_negative_pairs_w05.jsonl"
W05_METADATA = CALIBRATION_DIR / "hard_negative_pairs_w05.metadata.json"
FINAL_TEST = CALIBRATION_DIR / "final_test_dense_w05.json"
SOURCE = ROOT / "data" / "eval_official" / "topk_eval_official.jsonl"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected object")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_train_pairs(path: Path, metadata_path: Path) -> dict[str, Any]:
    metadata = _read_json(metadata_path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if metadata.get("source_split") != "train" or metadata.get("source_case_count") != 291:
        raise ValueError("hard-negative metadata must declare the 291-case train split")
    if metadata.get("source_file_sha256") != _sha256(SOURCE):
        raise ValueError("hard-negative source hash does not match the locked official source")
    if metadata.get("output_file_sha256") != _sha256(path):
        raise ValueError("hard-negative output hash mismatch")
    if metadata.get("pair_count") != len(rows):
        raise ValueError("hard-negative pair count mismatch")
    for row in rows:
        source_id = str(row.get("source_test_id") or "")
        if (
            row.get("source_split") != "train"
            or not source_id.startswith("train_")
            or row.get("training_use_only") is not True
        ):
            raise ValueError(f"non-train hard-negative row rejected: {source_id}")
    return {
        "pair_count": len(rows),
        "negative_outranks_positive_count": int(metadata["negative_outranks_positive_count"]),
        "gold_missing_top20_count": int(metadata["gold_missing_top20_count"]),
        "dense_available_case_count": int(metadata["dense_available_case_count"]),
        "source_file_sha256": metadata["source_file_sha256"],
        "output_file_sha256": metadata["output_file_sha256"],
    }


def select_val_result(paths: list[Path]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    experiments: list[dict[str, Any]] = []
    for path in paths:
        report = _read_json(path)
        metadata = report.get("evaluation_metadata", {})
        metric = report.get("topk_evaluation", {})
        if metadata.get("split") != "val" or metric.get("split") != "val":
            raise ValueError(f"calibration accepts val reports only: {path}")
        weight = float(metadata.get("dense_weight_override") or 0.0)
        try:
            report_path = path.relative_to(ROOT).as_posix()
        except ValueError:
            report_path = path.as_posix()
        experiments.append(
            {
                "weight": weight,
                "top3_pct": float(metric["top3_hit_rate_pct"]),
                "top5_pct": float(metric["top5_hit_rate_pct"]),
                "macro_top3_pct": float(metric["macro_by_gold_model_top3_pct"]),
                "macro_top5_pct": float(metric["macro_by_gold_model_top5_pct"]),
                "dense_coverage_pct": float(metric["retrieval_evidence"]["dense_case_coverage_pct"]),
                "report": report_path,
            }
        )
    if not experiments:
        raise ValueError("no validation experiments supplied")
    selected = max(
        experiments,
        key=lambda row: (
            row["top3_pct"], row["top5_pct"], row["macro_top3_pct"],
            row["macro_top5_pct"], -row["weight"],
        ),
    )
    return selected, sorted(experiments, key=lambda row: row["weight"])


def main() -> None:
    baseline_pairs = validate_train_pairs(TRAIN_PAIRS, TRAIN_METADATA)
    selected_pairs = validate_train_pairs(W05_PAIRS, W05_METADATA)
    selected, experiments = select_val_result(sorted(CALIBRATION_DIR.glob("val_dense_w*.json")))
    baseline = next(row for row in experiments if row["weight"] == 0.0)
    summary = {
        "selection_boundary": {
            "train_cases": 291,
            "val_cases": 64,
            "test_cases_read_for_selection": 0,
            "rule": "train hard negatives are diagnostic; dense weight is selected on val; test is frozen until one final confirmation",
        },
        "train_hard_negative_baseline": baseline_pairs,
        "train_hard_negative_selected_weight": selected_pairs,
        "validation_experiments": experiments,
        "selected": selected,
        "validation_improvement_vs_sparse": {
            "top3_points": round(selected["top3_pct"] - baseline["top3_pct"], 2),
            "top5_points": round(selected["top5_pct"] - baseline["top5_pct"], 2),
            "negative_outrank_reduction": (
                baseline_pairs["negative_outranks_positive_count"]
                - selected_pairs["negative_outranks_positive_count"]
            ),
        },
        "decision": "freeze_selected_weight_then_run_test_once_without_retuning",
    }
    if FINAL_TEST.exists():
        final_report = _read_json(FINAL_TEST)
        final_metadata = final_report.get("evaluation_metadata", {})
        final_metric = final_report.get("topk_evaluation", {})
        if final_metadata.get("split") != "test" or final_metric.get("split") != "test":
            raise ValueError("final confirmation report must use the test split")
        final_weight = float(final_metadata.get("dense_weight_override"))
        if final_weight != selected["weight"]:
            raise ValueError("final confirmation weight differs from the frozen val selection")
        summary["final_test_confirmation"] = {
            "used_for_selection": False,
            "weight": final_weight,
            "total": int(final_metric["total"]),
            "top3_pct": float(final_metric["top3_hit_rate_pct"]),
            "top5_pct": float(final_metric["top5_hit_rate_pct"]),
            "macro_top3_pct": float(final_metric["macro_by_gold_model_top3_pct"]),
            "macro_top5_pct": float(final_metric["macro_by_gold_model_top5_pct"]),
            "dense_coverage_pct": float(final_metric["retrieval_evidence"]["dense_case_coverage_pct"]),
            "per_scenario": final_metric["per_scenario"],
            "report": FINAL_TEST.relative_to(ROOT).as_posix(),
            "retuning_after_test": False,
        }
    output = CALIBRATION_DIR / "hybrid_calibration_summary.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
