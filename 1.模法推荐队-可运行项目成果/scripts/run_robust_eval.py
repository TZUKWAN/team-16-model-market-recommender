#!/usr/bin/env python3
"""Run robustness evaluation on perturbed official questions."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.demand_parser import DemandParser  # noqa: E402
from app.services.recommender import ModelRecommendationService  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_PATH = BASE_DIR / "data" / "eval_robustness" / "robust_eval.jsonl"
REPORT_DIR = BASE_DIR / "reports" / "robustness"
RESULT_PATH = REPORT_DIR / "robust_eval_results.json"
FAILURE_PATH = REPORT_DIR / "robust_failures.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def pct(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def evaluate(
    records: list[dict[str, Any]],
    limit: int | None = None,
    use_llm: bool | None = None,
    use_keyword_rules: bool | None = None,
) -> dict[str, Any]:
    """Run robustness evaluation.

    ``use_llm`` / ``use_keyword_rules`` are forwarded to ``recommend()`` for
    ablation; when ``None`` the legacy behavior is preserved.
    """
    if limit is not None:
        records = records[:limit]

    parser = DemandParser()
    recommender = ModelRecommendationService()
    totals = defaultdict(lambda: {"total": 0, "intent": 0, "top3": 0, "top5": 0})
    failures: list[dict[str, Any]] = []

    for record in records:
        query = record["query"]
        gold_domain = record.get("expected_domain", "")
        gold_id = record.get("gold_model_id", "")
        gold_name = record.get("gold_model_name", "")
        perturbation_type = record.get("perturbation_type", "unknown")

        parsed = parser.parse(query, use_llm=use_llm)
        parse_dict = parsed.model_dump()
        parse_dict["model_source"] = "official"
        recommended = recommender.recommend(
            parse_dict,
            top_k=5,
            use_llm=use_llm,
            use_keyword_rules=use_keyword_rules,
        )
        recommended_ids = [item.model_id for item in recommended.recommendations]
        recommended_names = [item.model_name for item in recommended.recommendations]

        intent_hit = parsed.intent == gold_domain
        top3_hit = gold_id in recommended_ids[:3] or gold_name in recommended_names[:3]
        top5_hit = gold_id in recommended_ids or gold_name in recommended_names

        for bucket in ("overall", perturbation_type):
            totals[bucket]["total"] += 1
            totals[bucket]["intent"] += int(intent_hit)
            totals[bucket]["top3"] += int(top3_hit)
            totals[bucket]["top5"] += int(top5_hit)

        if not (intent_hit and top5_hit):
            failures.append({
                "robust_id": record.get("robust_id", ""),
                "perturbation_type": perturbation_type,
                "query": query,
                "original_query": record.get("original_query", ""),
                "gold_domain": gold_domain,
                "predicted_domain": parsed.intent,
                "gold_model_id": gold_id,
                "gold_model_name": gold_name,
                "recommended_top5_ids": recommended_ids,
                "recommended_top5_names": recommended_names,
                "intent_hit": intent_hit,
                "top3_hit": top3_hit,
                "top5_hit": top5_hit,
            })

    metrics = {}
    for bucket, values in totals.items():
        total = values["total"]
        metrics[bucket] = {
            "total": total,
            "intent_accuracy_pct": pct(values["intent"], total),
            "top3_hit_rate_pct": pct(values["top3"], total),
            "top5_hit_rate_pct": pct(values["top5"], total),
        }

    overall = metrics.get("overall", {"total": 0})
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_size": len(records),
        "metrics": metrics,
        "failure_count": len(failures),
        "acceptable_thresholds": {
            "intent_accuracy_pct": 85.0,
            "top3_hit_rate_pct": 75.0,
            "top5_hit_rate_pct": 85.0,
        },
        "passed": (
            overall.get("intent_accuracy_pct", 0) >= 85.0
            and overall.get("top3_hit_rate_pct", 0) >= 75.0
            and overall.get("top5_hit_rate_pct", 0) >= 85.0
        ),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ablation", action="store_true",
                        help="Run rule_only vs llm_on ablation (writes reports/ablation/)")
    args = parser.parse_args()

    if not args.data.exists():
        raise SystemExit(f"Robustness dataset not found: {args.data}. Run scripts/generate_robust_eval.py first.")

    records = load_jsonl(args.data)

    if args.ablation:
        # Compare how rule-only vs LLM-on paths degrade under each perturbation
        # type. The headline finding is the per-bucket delta: LLM paths are
        # expected to retain more accuracy under synonym/typo/colloquial noise.
        ablation_modes = {
            "rule_only": {"use_llm": False},
            "llm_on": {"use_llm": True},
        }
        ablation_summary: dict[str, Any] = {}
        for mode_name, flags in ablation_modes.items():
            res = evaluate(records, limit=args.limit, **flags)
            ablation_summary[mode_name] = {
                "metrics": {b: {k: v for k, v in m.items()} for b, m in res["metrics"].items()},
                "failure_count": res["failure_count"],
            }
            print(f"[ablation {mode_name}] overall intent={res['metrics'].get('overall', {}).get('intent_accuracy_pct', 0)}% "
                  f"top3={res['metrics'].get('overall', {}).get('top3_hit_rate_pct', 0)}% "
                  f"top5={res['metrics'].get('overall', {}).get('top5_hit_rate_pct', 0)}%")

        ablation_dir = BASE_DIR / "reports" / "ablation"
        ablation_dir.mkdir(parents=True, exist_ok=True)
        ablation_path = ablation_dir / "ablation_robust.json"
        ablation_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "dataset_size": len(records),
                    "modes": ablation_summary,
                    "note": ("Per-perturbation hit rate under rule_only vs llm_on. "
                             "A smaller accuracy drop for llm_on across "
                             "synonym/typo_noise/colloquial buckets indicates the LLM "
                             "path generalizes better than memorized keyword rules."),
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Ablation saved to: {ablation_path}")
        return 0

    result = evaluate(records, limit=args.limit)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    serializable = {k: v for k, v in result.items() if k != "failures"}
    RESULT_PATH.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(FAILURE_PATH, result["failures"])

    overall = serializable["metrics"].get("overall", {})
    print("ROBUSTNESS EVALUATION")
    print(f"Dataset size: {serializable['dataset_size']}")
    print(f"Intent Accuracy: {overall.get('intent_accuracy_pct', 0)}%")
    print(f"Top3 Hit Rate: {overall.get('top3_hit_rate_pct', 0)}%")
    print(f"Top5 Hit Rate: {overall.get('top5_hit_rate_pct', 0)}%")
    print(f"Failures: {serializable['failure_count']}")
    print(f"Passed thresholds: {serializable['passed']}")
    print(f"Results saved to: {RESULT_PATH}")
    print(f"Failures saved to: {FAILURE_PATH}")
    return 0 if serializable["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
