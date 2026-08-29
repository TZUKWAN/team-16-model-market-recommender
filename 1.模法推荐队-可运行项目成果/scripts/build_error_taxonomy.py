#!/usr/bin/env python3
"""Build a train/val-only recommendation error taxonomy and regression set."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.repositories.model_asset_repository import get_model_asset_repository


OUTPUT_DIR = ROOT / "reports" / "error_taxonomy"
REQUIRED_CATEGORIES = (
    "domain_confusion",
    "stage_confusion",
    "segment_confusion",
    "output_confusion",
    "similar_model_confusion",
    "llm_illegal_id",
    "data_gap_misjudgment",
)
CONTRACT_REGRESSION_TESTS = {
    "segment_confusion": ["backend/tests/test_error_taxonomy.py::test_classifies_metadata_confusion_and_illegal_id"],
    "llm_illegal_id": [
        "backend/tests/test_llm_rerank.py::test_llm_rerank_discards_illegal_model_ids_and_keeps_candidate_set",
        "backend/tests/test_script_validation.py::test_validation_rejects_illegal_model_ids",
    ],
    "data_gap_misjudgment": [
        "backend/tests/test_error_taxonomy.py::test_classifies_metadata_confusion_and_illegal_id",
        "backend/tests/test_reports.py::TestReportGeneration::test_data_gap_section",
    ],
}


def _as_set(value: Any) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "").strip()
    return {text} if text else set()


def _union(models: list[dict[str, Any]], field: str) -> set[str]:
    values: set[str] = set()
    for model in models:
        values.update(_as_set(model.get(field)))
    return values


def classify_failure(
    top_model_ids: list[str],
    gold_model_id: str,
    *,
    repository: Any | None = None,
) -> dict[str, Any]:
    """Classify one Top3 miss using factual model metadata only."""
    repo = repository or get_model_asset_repository()
    gold = repo.get_model(gold_model_id)
    if gold is None:
        return {"categories": ["gold_model_not_in_repo"], "illegal_model_ids": []}

    illegal_ids = [model_id for model_id in top_model_ids[:5] if repo.get_model(model_id) is None]
    top_models = [repo.get_model(model_id) for model_id in top_model_ids[:3]]
    top_models = [model for model in top_models if model is not None]
    categories: list[str] = []
    if illegal_ids:
        categories.append("llm_illegal_id")

    gold_domain = str(gold.get("domain") or "")
    top_domains = {str(model.get("domain") or "") for model in top_models if model.get("domain")}
    if gold_domain and top_domains and gold_domain not in top_domains:
        categories.append("domain_confusion")
    elif gold_model_id not in top_model_ids[:3] and gold_domain in top_domains:
        categories.append("similar_model_confusion")

    top1_models = top_models[:1]
    feature_checks = (
        ("business_stage", "stage_confusion"),
        ("customer_segment", "segment_confusion"),
        ("output_fields", "output_confusion"),
        ("input_fields_required", "data_gap_misjudgment"),
    )
    comparisons: dict[str, dict[str, list[str]]] = {}
    for field, category in feature_checks:
        gold_values = _as_set(gold.get(field))
        top_values = _union(top1_models, field)
        comparisons[field] = {
            "gold": sorted(gold_values),
            "top1": sorted(top_values),
        }
        if gold_values and top_values and not gold_values.intersection(top_values):
            categories.append(category)

    readiness = gold.get("data_readiness_score")
    if isinstance(readiness, (int, float)) and readiness < 50 and "data_gap_misjudgment" not in categories:
        categories.append("data_gap_misjudgment")
    if not categories:
        categories.append("ranking_low")
    return {
        "categories": categories,
        "illegal_model_ids": illegal_ids,
        "gold_domain": gold_domain,
        "top3_domains": sorted(top_domains),
        "comparisons": comparisons,
        "gold_data_readiness_score": readiness,
    }


def _load_report(path: Path) -> tuple[str, dict[str, Any]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    metadata = report.get("evaluation_metadata", {})
    metric = report.get("topk_evaluation", {})
    split = str(metadata.get("split") or metric.get("split") or "")
    if split not in {"train", "val"}:
        raise ValueError(f"regression taxonomy accepts train/val only: {path} ({split})")
    if metric.get("split") != split:
        raise ValueError(f"report split mismatch: {path}")
    return split, metric


def build_taxonomy(report_paths: list[Path], *, repository: Any | None = None) -> dict[str, Any]:
    repo = repository or get_model_asset_repository()
    failures: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {category: 0 for category in REQUIRED_CATEGORIES}
    split_metrics: dict[str, dict[str, Any]] = {}

    for path in report_paths:
        split, metric = _load_report(path)
        split_metrics[split] = {
            "total": metric["total"],
            "top3_pct": metric["top3_hit_rate_pct"],
            "top5_pct": metric["top5_hit_rate_pct"],
            "macro_top3_pct": metric["macro_by_gold_model_top3_pct"],
            "macro_top5_pct": metric["macro_by_gold_model_top5_pct"],
            "report": path.relative_to(ROOT).as_posix(),
        }
        for detail in metric.get("details", []):
            if detail.get("top3_hit"):
                continue
            top_ids = [str(item) for item in detail.get("recommended_top5_ids", [])]
            gold_id = str(detail.get("gold_id") or "")
            classification = classify_failure(top_ids, gold_id, repository=repo)
            for category in classification["categories"]:
                category_counts[category] = category_counts.get(category, 0) + 1
            failures.append(
                {
                    "split": split,
                    "test_id": detail.get("test_id", ""),
                    "query": str(detail.get("query") or "")[:160],
                    "gold_model_id": gold_id,
                    "gold_model_name": detail.get("gold_name", ""),
                    "predicted_top5": top_ids,
                    "gold_rank_in_top5": detail.get("gold_rank_in_returned_top5"),
                    "top5_hit": bool(detail.get("top5_hit")),
                    "error_categories": classification["categories"],
                    "classification_evidence": {
                        key: value for key, value in classification.items() if key != "categories"
                    },
                }
            )

    regression_set = {
        category: [
            failure for failure in failures if category in failure["error_categories"]
        ][:5]
        for category in REQUIRED_CATEGORIES
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_splits": sorted(split_metrics),
        "test_cases_used": 0,
        "split_metrics": split_metrics,
        "failure_count": len(failures),
        "category_counts": category_counts,
        "category_coverage": {
            category: (
                "observed_train_val"
                if category_counts.get(category, 0)
                else "contract_test_only"
                if CONTRACT_REGRESSION_TESTS.get(category)
                else "not_observed"
            )
            for category in REQUIRED_CATEGORIES
        },
        "contract_regression_tests": CONTRACT_REGRESSION_TESTS,
        "regression_set": regression_set,
        "all_failures": failures,
        "notes": {
            "llm_illegal_id": "LLM is disabled in these reports; classifier and constrained-generation unit tests cover this category.",
            "data_gap_misjudgment": "Assigned only when factual required-input sets of gold and incorrect Top1 are disjoint, or a factual data_readiness_score is below 50; missing fields are not guessed.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reports",
        nargs="+",
        default=[
            "reports/calibration/train_dense_w05.json",
            "reports/calibration/val_dense_w05.json",
        ],
    )
    parser.add_argument("--output", default="reports/error_taxonomy/error_taxonomy_train_val.json")
    args = parser.parse_args()
    paths = [Path(item) if Path(item).is_absolute() else ROOT / item for item in args.reports]
    taxonomy = build_taxonomy(paths)
    output = Path(args.output) if Path(args.output).is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built train/val taxonomy with {taxonomy['failure_count']} Top3 failures")
    print(json.dumps(taxonomy["category_counts"], ensure_ascii=False, sort_keys=True))
    print(f"Saved to: {output}")


if __name__ == "__main__":
    main()
