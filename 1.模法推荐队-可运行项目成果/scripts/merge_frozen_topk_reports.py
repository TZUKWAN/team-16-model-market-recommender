"""Merge frozen train/val/test TopK reports without re-running any split."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_official_eval import compute_provenance


SPLIT_REPORTS = {
    "train": ROOT / "reports" / "calibration" / "train_dense_w05.json",
    "val": ROOT / "reports" / "calibration" / "val_dense_w05.json",
    "test": ROOT / "reports" / "calibration" / "final_test_dense_w05.json",
}
OUTPUT = ROOT / "reports" / "official" / "eval_official_results.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _merge_buckets(metrics: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, int]] = {}
    for metric in metrics:
        for key, row in metric[field].items():
            bucket = merged.setdefault(key, {"total": 0, "top3_hits": 0, "top5_hits": 0})
            bucket["total"] += int(row["total"])
            bucket["top3_hits"] += int(row["top3_hits"])
            bucket["top5_hits"] += int(row["top5_hits"])
    return {
        key: {
            **bucket,
            "top3_hit_rate_pct": round(bucket["top3_hits"] / bucket["total"] * 100, 2),
            "top5_hit_rate_pct": round(bucket["top5_hits"] / bucket["total"] * 100, 2),
        }
        for key, bucket in sorted(merged.items())
    }


def merge_topk_reports(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    metrics: list[dict[str, Any]] = []
    for expected_split in ("train", "val", "test"):
        report = reports[expected_split]
        metadata = report.get("evaluation_metadata", {})
        metric = report.get("topk_evaluation", {})
        if metadata.get("split") != expected_split or metric.get("split") != expected_split:
            raise ValueError(f"frozen report split mismatch: {expected_split}")
        if float(metadata.get("dense_weight_override")) != 0.5:
            raise ValueError(f"frozen report weight mismatch: {expected_split}")
        metrics.append(metric)

    total = sum(int(metric["total"]) for metric in metrics)
    top3_hits = sum(int(metric["top3_hits"]) for metric in metrics)
    top5_hits = sum(int(metric["top5_hits"]) for metric in metrics)
    per_model = _merge_buckets(metrics, "per_gold_model")
    per_scenario = _merge_buckets(metrics, "per_scenario")
    dense_available = sum(
        int(metric["retrieval_evidence"]["dense_available_case_count"]) for metric in metrics
    )
    return {
        "metric": "topk_hit_rate",
        "total": total,
        "top3_hits": top3_hits,
        "top5_hits": top5_hits,
        "top3_hit_rate_pct": round(top3_hits / total * 100, 2),
        "top5_hit_rate_pct": round(top5_hits / total * 100, 2),
        "macro_by_gold_model_top3_pct": round(
            sum(row["top3_hit_rate_pct"] for row in per_model.values()) / len(per_model), 2
        ),
        "macro_by_gold_model_top5_pct": round(
            sum(row["top5_hit_rate_pct"] for row in per_model.values()) / len(per_model), 2
        ),
        "gold_model_coverage_count": len(per_model),
        "per_gold_model": per_model,
        "per_scenario": per_scenario,
        "split": "all",
        "pipeline": {
            "use_llm_requested": False,
            "parser_use_llm": False,
            "rerank_use_llm": False,
            "use_keyword_rules": False,
            "use_hybrid_retrieval": True,
            "dense_enabled": True,
            "dense_weight": 0.5,
            "dense_model": "BAAI/bge-m3",
        },
        "llm_evidence": {
            "parser_llm_count": 0,
            "parser_fallback_count": sum(
                int(metric["llm_evidence"]["parser_fallback_count"]) for metric in metrics
            ),
            "rerank_attempt_count": 0,
            "rerank_success_count": 0,
            "trace_case_count": 0,
            "trace_case_coverage_pct": 0.0,
            "unique_trace_count": 0,
        },
        "retrieval_evidence": {
            "dense_requested_case_count": total,
            "dense_available_case_count": dense_available,
            "dense_case_coverage_pct": round(dense_available / total * 100, 2),
            "retrieval_mode_counts": {"sparse+dense": total},
            "dense_model": "BAAI/bge-m3",
            "dense_weight": 0.5,
        },
        "details": [detail for metric in metrics for detail in metric["details"]],
        "derived_from_frozen_splits": True,
    }


def main() -> None:
    base = _load(OUTPUT)
    split_payloads = {split: _load(path) for split, path in SPLIT_REPORTS.items()}
    base["topk_evaluation"] = merge_topk_reports(split_payloads)
    base["evaluation_metadata"] = {
        "generated_at": datetime.now().isoformat(),
        "split": "all",
        "llm_mode": "off",
        "llm_scope": "rerank",
        "keyword_rules": False,
        "hybrid_retrieval": True,
        "dense_retrieval_override": "on",
        "dense_weight_override": 0.5,
        "provenance": compute_provenance(),
        "split_responsibility": {
            "train_count": 291,
            "val_count": 64,
            "test_count": 62,
            "all_count": 417,
            "rule": "train/val selected the frozen config; test was run once; this report is arithmetic aggregation without re-executing test",
        },
        "aggregation": {
            "method": "merge frozen split details and recompute counts",
            "test_reexecuted": False,
            "sources": {
                split: {"path": path.relative_to(ROOT).as_posix(), "sha256": _hash(path)}
                for split, path in SPLIT_REPORTS.items()
            },
        },
    }
    OUTPUT.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metric = base["topk_evaluation"]
    print(
        f"Merged frozen TopK: {metric['total']} cases, "
        f"Top3={metric['top3_hit_rate_pct']}%, Top5={metric['top5_hit_rate_pct']}%"
    )


if __name__ == "__main__":
    main()
