#!/usr/bin/env python3
"""run_ablation_eval.py - One-shot rule-vs-LLM ablation report.

This script directly drives ``ModelRecommendationService.recommend()`` with the
``use_llm`` / ``use_keyword_rules`` ablation switches (no shell-out to the
sub-scripts), so the comparison uses identical data in a single run.

It produces a consolidated report answering two defense questions:
  1. "How much do the hardcoded keyword rules contribute to the 97% headline?"
  2. "Does the LLM path generalize better than keyword rules under perturbation?"

Output: ``reports/ablation/ablation_report.json`` + a printed comparison table.

Usage:
    python scripts/run_ablation_eval.py
    python scripts/run_ablation_eval.py --robust-limit 400   # cap robust samples for speed
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from app.services.demand_parser import DemandParser  # noqa: E402
from app.services.recommender import ModelRecommendationService  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent.parent
OFFICIAL_TOPK = BASE_DIR / "data" / "eval_official" / "topk_eval_official.jsonl"
ROBUST_DATA = BASE_DIR / "data" / "eval_robustness" / "robust_eval.jsonl"
ABLATION_DIR = BASE_DIR / "reports" / "ablation"
REPORT_PATH = ABLATION_DIR / "ablation_report.json"

# The four configurations of interest for the headline question.
OFFICIAL_MODES = {
    "legacy": {},  # default flags
    "rule_only": {"use_llm": False},
    "llm_on": {"use_llm": True},
    "keyword_off": {"use_keyword_rules": False},
    "rule_only_no_keyword": {"use_llm": False, "use_keyword_rules": False},
}
# For robustness we compare the two ranking strategies end-to-end.
ROBUST_MODES = {
    "rule_only": {"use_llm": False},
    "llm_on": {"use_llm": True},
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def eval_official_topk(
    samples: list[dict[str, Any]],
    recommender: ModelRecommendationService,
    parser: DemandParser,
    flags: dict[str, Any],
) -> dict[str, Any]:
    top3_hits = top5_hits = 0
    total = 0
    for s in samples:
        query = s.get("query", "")
        gold_id = s.get("gold_model_id", "")
        gold_name = s.get("gold_model_name", "")
        if not query or not gold_id:
            continue
        parse_dict = parser.parse(query, use_llm=flags.get("use_llm")).model_dump()
        parse_dict["model_source"] = "official"
        result = recommender.recommend(parse_dict, top_k=5, **flags)
        rec_ids = [r.model_id for r in result.recommendations]
        rec_names = [r.model_name for r in result.recommendations]
        if gold_id in rec_ids[:3] or gold_name in rec_names[:3]:
            top3_hits += 1
        if gold_id in rec_ids or gold_name in rec_names:
            top5_hits += 1
        total += 1
    return {
        "total": total,
        "top3_hit_rate_pct": pct(top3_hits, total),
        "top5_hit_rate_pct": pct(top5_hits, total),
        "top3_hits": top3_hits,
        "top5_hits": top5_hits,
    }


def eval_robust(
    records: list[dict[str, Any]],
    recommender: ModelRecommendationService,
    parser: DemandParser,
    flags: dict[str, Any],
) -> dict[str, Any]:
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "intent": 0, "top3": 0, "top5": 0})
    for record in records:
        query = record["query"]
        gold_domain = record.get("expected_domain", "")
        gold_id = record.get("gold_model_id", "")
        gold_name = record.get("gold_model_name", "")
        ptype = record.get("perturbation_type", "unknown")
        parsed = parser.parse(query, use_llm=flags.get("use_llm"))
        parse_dict = parsed.model_dump()
        parse_dict["model_source"] = "official"
        recommended = recommender.recommend(parse_dict, top_k=5, **flags)
        rec_ids = [item.model_id for item in recommended.recommendations]
        rec_names = [item.model_name for item in recommended.recommendations]
        intent_hit = parsed.intent == gold_domain
        top3_hit = gold_id in rec_ids[:3] or gold_name in rec_names[:3]
        top5_hit = gold_id in rec_ids or gold_name in rec_names
        for bucket in ("overall", ptype):
            buckets[bucket]["total"] += 1
            buckets[bucket]["intent"] += int(intent_hit)
            buckets[bucket]["top3"] += int(top3_hit)
            buckets[bucket]["top5"] += int(top5_hit)
    metrics = {}
    for bucket, v in buckets.items():
        metrics[bucket] = {
            "total": v["total"],
            "intent_accuracy_pct": pct(v["intent"], v["total"]),
            "top3_hit_rate_pct": pct(v["top3"], v["total"]),
            "top5_hit_rate_pct": pct(v["top5"], v["total"]),
        }
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser(description="Consolidated rule-vs-LLM ablation report.")
    ap.add_argument("--robust-limit", type=int, default=None,
                    help="Cap robustness samples per run for speed.")
    ap.add_argument("--skip-robust", action="store_true", help="Skip the robustness portion.")
    args = ap.parse_args()

    ABLATION_DIR.mkdir(parents=True, exist_ok=True)
    parser = DemandParser()
    recommender = ModelRecommendationService()

    print("=" * 64)
    print("ABLATION EVALUATION (rule vs LLM)")
    print("=" * 64)

    # ---- Official TopK ----
    official_samples = load_jsonl(OFFICIAL_TOPK)
    official_results: dict[str, Any] = {}
    print(f"\n[1/2] Official TopK  (samples={len(official_samples)})")
    print(f"{'mode':<24}{'top3%':>10}{'top5%':>10}")
    print("-" * 44)
    for mode_name, flags in OFFICIAL_MODES.items():
        r = eval_official_topk(official_samples, recommender, parser, flags)
        official_results[mode_name] = r
        print(f"{mode_name:<24}{r['top3_hit_rate_pct']:>10}{r['top5_hit_rate_pct']:>10}")

    # ---- Robustness ----
    robust_results: dict[str, Any] = {}
    robust_note = ""
    if not args.skip_robust:
        robust_records = load_jsonl(ROBUST_DATA)
        if args.robust_limit:
            robust_records = robust_records[: args.robust_limit]
        print(f"\n[2/2] Robustness  (samples={len(robust_records)})")
        for mode_name, flags in ROBUST_MODES.items():
            robust_results[mode_name] = eval_robust(
                robust_records, recommender, parser, flags
            )
        # Build a per-bucket delta table (llm_on - rule_only).
        deltas: dict[str, dict[str, float]] = {}
        rule = robust_results.get("rule_only", {})
        llm = robust_results.get("llm_on", {})
        for bucket in set(rule) | set(llm):
            rb = rule.get(bucket, {})
            lb = llm.get(bucket, {})
            deltas[bucket] = {
                "intent_delta": round(lb.get("intent_accuracy_pct", 0) - rb.get("intent_accuracy_pct", 0), 2),
                "top3_delta": round(lb.get("top3_hit_rate_pct", 0) - rb.get("top3_hit_rate_pct", 0), 2),
                "top5_delta": round(lb.get("top5_hit_rate_pct", 0) - rb.get("top5_hit_rate_pct", 0), 2),
            }
        robust_note = (
            "Positive deltas (llm_on - rule_only) under synonym/typo_noise/colloquial "
            "buckets indicate the LLM ranking path generalizes better than memorized "
            "keyword rules, i.e. the system is not merely overfitting the closed set."
        )
        print("\nPer-bucket delta (llm_on - rule_only), positive = LLM better:")
        print(f"{'bucket':<20}{'intent':>10}{'top3':>10}{'top5':>10}")
        print("-" * 50)
        for bucket, d in sorted(deltas.items()):
            print(f"{bucket:<20}{d['intent_delta']:>10}{d['top3_delta']:>10}{d['top5_delta']:>10}")
        robust_results["_deltas_llm_minus_rule"] = deltas

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "official_topk": official_results,
        "robust": robust_results,
        "robust_note": robust_note,
        "llm_available": getattr(recommender.llm, "available", False),
        "llm_provider": getattr(recommender.llm, "provider", ""),
        "llm_model": getattr(recommender.llm, "model", ""),
        "interpretation": (
            "official_topk shows the isolated contribution of keyword rules vs LLM to the "
            "headline accuracy. robust shows whether the LLM path degrades less under input "
            "perturbation. Together they answer 'is the accuracy real LLM understanding or "
            "memorized keyword rules?'."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved to: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
