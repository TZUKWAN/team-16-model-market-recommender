#!/usr/bin/env python3
"""Refresh the frontend-facing official TopK reports from current dense eval runs.

The evaluation page (backend/app/api/v1/official_evaluation.py) reads four files
under reports/official_eval/ with the schema produced by the legacy
evaluate_official_topk.py. Those files were last generated on 2026-06-30 with the
pre-BGE sparse pipeline and went stale. This script converts the current
competition_dense TopK results (reports/audit/official_eval_{val,test}_20260722.json,
produced by run_official_eval.py) back into that legacy schema so the page shows
the same current dense metrics as reports/official and reports/audit.

It never hand-edits numbers: every value is computed from the input eval JSONs.
It only writes the five files it owns and preserves any other evidence in the
output directory.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAL = ROOT / "reports" / "audit" / "official_eval_val_20260722.json"
DEFAULT_TEST = ROOT / "reports" / "audit" / "official_eval_test_20260722.json"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "official_eval"

FAILURE_TYPES = (
    "confused_model",
    "keyword_missing",
    "business_scenario_mismatch",
    "semantic_similar_but_wrong",
    "metadata_gap",
    "unknown",
)


def _rate(hits: int, total: int) -> float:
    return round(hits / total * 100, 1) if total else 0.0


def _recommended_models(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Legacy shape used by the page only for id->name resolution.

    The current pipeline deliberately hides internal scores from user-facing
    surfaces, so score/matched_keywords are emitted as neutral placeholders;
    the page does not render them.
    """
    ids = row.get("recommended_top5_ids") or []
    names = row.get("recommended_top5_names") or []
    models = []
    for index, model_id in enumerate(ids):
        models.append({
            "model_id": model_id,
            "model_name": names[index] if index < len(names) else model_id,
            "score": 0.0,
            "matched_keywords": [],
            "source_type": "official_dataset",
        })
    return models


def _classify_failure(row: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (failure_type, failure_scope, reason, suggested_fix) for a miss."""
    if row.get("top1_hit"):
        return None, None, None, None
    gold_id = row.get("gold_id", "")
    gold_name = row.get("gold_name", "")
    rank = row.get("gold_rank_in_returned_top5")
    if not row.get("top5_hit"):
        scope = "top5_miss"
        failure_type = "unknown"
        reason = (
            f"Gold model '{gold_name}' ({gold_id}) is not in the returned top5 "
            "under the current competition_dense pipeline."
        )
        suggested_fix = (
            "Review query-gold alignment and retrieval coverage for this case; "
            "do not tune against the test split."
        )
    elif not row.get("top3_hit"):
        scope = "top3_miss"
        failure_type = "confused_model"
        reason = (
            f"Gold model '{gold_name}' ({gold_id}) appears at rank {rank} "
            "(outside top3) under the current competition_dense pipeline."
        )
        suggested_fix = "Improve inter-class discrimination for near-neighbor official models."
    else:
        scope = "top1_miss"
        failure_type = "confused_model"
        reason = (
            f"Gold model '{gold_name}' ({gold_id}) appears at rank {rank} "
            "(not top1) under the current competition_dense pipeline."
        )
        suggested_fix = "Improve inter-class discrimination for near-neighbor official models."
    return failure_type, scope, reason, suggested_fix


def _convert_split(eval_report: dict[str, Any], split: str) -> dict[str, Any]:
    topk = eval_report["topk_evaluation"]
    rows = []
    for detail in topk.get("details", []):
        failure_type, _scope, _reason, _fix = _classify_failure(detail)
        rows.append({
            "query_id": detail.get("test_id", ""),
            "split": split,
            "query": detail.get("query", ""),
            "gold_model_ids": [detail.get("gold_id", "")],
            "gold_model_names": [detail.get("gold_name", "")],
            "recommended_top5": detail.get("recommended_top5_ids") or [],
            "recommended_models": _recommended_models(detail),
            "top1_hit": bool(detail.get("top1_hit")),
            "top3_hit": bool(detail.get("top3_hit")),
            "top5_hit": bool(detail.get("top5_hit")),
            "failure_type": failure_type,
        })
    total = int(topk.get("total", len(rows)))
    return {
        "split": split,
        "total": total,
        "top1_hits": int(topk.get("top1_hits", sum(1 for r in rows if r["top1_hit"]))),
        "top3_hits": int(topk.get("top3_hits", 0)),
        "top5_hits": int(topk.get("top5_hits", 0)),
        "top1_rate": _rate(int(topk.get("top1_hits", 0)), total),
        "top3_rate": _rate(int(topk.get("top3_hits", 0)), total),
        "top5_rate": _rate(int(topk.get("top5_hits", 0)), total),
        "results": rows,
    }


def _failures(val_results: dict[str, Any], test_results: dict[str, Any]) -> list[dict[str, Any]]:
    failures = []
    for split_results in (val_results, test_results):
        # Map query text back from the results rows (details carry it verbatim).
        for row in split_results["results"]:
            if row["top1_hit"]:
                continue
            failure_type, scope, reason, suggested_fix = _classify_failure({
                "top1_hit": row["top1_hit"],
                "top3_hit": row["top3_hit"],
                "top5_hit": row["top5_hit"],
                "gold_id": row["gold_model_ids"][0] if row["gold_model_ids"] else "",
                "gold_name": row["gold_model_names"][0] if row["gold_model_names"] else "",
                "gold_rank_in_returned_top5": (
                    (row["recommended_top5"].index(row["gold_model_ids"][0]) + 1)
                    if row["gold_model_ids"] and row["gold_model_ids"][0] in row["recommended_top5"]
                    else None
                ),
            })
            failures.append({
                **row,
                "failure_type": failure_type,
                "failure_scope": scope,
                "reason": reason,
                "suggested_fix": suggested_fix,
            })
    return failures


def _attribution(failures: list[dict[str, Any]]) -> dict[str, Any]:
    per_split: dict[str, Counter] = {"val": Counter(), "test": Counter()}
    for failure in failures:
        per_split[failure["split"]][failure["failure_type"]] += 1
    total = per_split["val"] + per_split["test"]
    return {
        "val": {key: per_split["val"].get(key, 0) for key in FAILURE_TYPES},
        "test": {key: per_split["test"].get(key, 0) for key in FAILURE_TYPES},
        "total": {key: total.get(key, 0) for key in FAILURE_TYPES},
    }


def _summary(val_results: dict[str, Any], test_results: dict[str, Any],
             failures: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "models": "data/official_60/models.jsonl",
            "val_queries": "data/official_60/queries_val.jsonl",
            "test_queries": "data/official_60/queries_test.jsonl",
            "pipeline": (
                "competition_dense (BGE-M3, 1024-dim, manifest verified) via "
                "scripts/run_official_eval.py; converted by "
                "scripts/refresh_official_eval_reports.py"
            ),
        },
        # Legacy headline mirrors the val split rates.
        "top1_accuracy": val_results["top1_rate"],
        "top3_accuracy": val_results["top3_rate"],
        "top5_accuracy": val_results["top5_rate"],
        "val": {key: val_results[key] for key in (
            "total", "top1_hits", "top3_hits", "top5_hits",
            "top1_rate", "top3_rate", "top5_rate",
        )},
        "test": {key: test_results[key] for key in (
            "total", "top1_hits", "top3_hits", "top5_hits",
            "top1_rate", "top3_rate", "top5_rate",
        )},
        "failure_attribution": _attribution(failures),
    }


def _report_markdown(summary: dict[str, Any]) -> str:
    val = summary["val"]
    test = summary["test"]
    return (
        "# 官方 TopK 评测报告（当前 competition_dense 口径）\n\n"
        f"生成时间：{summary['generated_at']}\n\n"
        "数据源：scripts/run_official_eval.py 在 competition_dense（BGE-M3，1024 维，"
        "清单已校验）下的 val/test 实跑结果，由 scripts/refresh_official_eval_reports.py "
        "转换为页面读取格式。与 reports/official、reports/audit 的口径一致；"
        "2026-06-30 的稀疏口径旧文件已被本报告取代。\n\n"
        "| 划分 | 样本数 | Top1 | Top3 | Top5 |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| val | {val['total']} | {val['top1_rate']}% | {val['top3_rate']}% | {val['top5_rate']}% |\n"
        f"| test | {test['total']} | {test['top1_rate']}% | {test['top3_rate']}% | {test['top5_rate']}% |\n\n"
        "说明：TopK 为对已知官方 60 模型目录和已公开 417 问题分布的检索命中率；"
        "test 已历史暴露，不是严格盲测集。\n"
    )


OWNED_FILES = (
    "official_topk_summary.json",
    "val_results.json",
    "test_results.json",
    "official_failures.json",
    "official_topk_report.md",
)


def refresh(val_path: Path, test_path: Path, output_dir: Path) -> dict[str, Any]:
    val_report = json.loads(val_path.read_text(encoding="utf-8"))
    test_report = json.loads(test_path.read_text(encoding="utf-8"))
    val_results = _convert_split(val_report, "val")
    test_results = _convert_split(test_report, "test")
    failures = _failures(val_results, test_results)
    summary = _summary(val_results, test_results, failures)

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "official_topk_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (output_dir / "val_results.json").write_text(
        json.dumps(val_results, ensure_ascii=False, indent=1), encoding="utf-8")
    (output_dir / "test_results.json").write_text(
        json.dumps(test_results, ensure_ascii=False, indent=1), encoding="utf-8")
    (output_dir / "official_failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")
    (output_dir / "official_topk_report.md").write_text(
        _report_markdown(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--val", type=Path, default=DEFAULT_VAL)
    parser.add_argument("--test", type=Path, default=DEFAULT_TEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = refresh(args.val, args.test, args.output_dir)
    print(json.dumps({
        "val": summary["val"],
        "test": summary["test"],
        "output_dir": str(args.output_dir),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
