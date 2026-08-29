#!/usr/bin/env python
"""
evaluate_official_topk.py — Evaluate OfficialRecommender Top1/Top3/Top5 hit rates
on val/test queries of the official_60 dataset, with failure attribution.

Outputs 5 files to reports/official_eval/:
  - official_topk_summary.json
  - official_topk_report.md
  - val_results.json
  - test_results.json
  - official_failures.json

Usage:
    python scripts/evaluate_official_topk.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure backend is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.official_recommender import OfficialRecommender

REPORTS_DIR = ROOT / "reports" / "official_eval"
DATA_DIR = ROOT / "data" / "official_60"

_FAILURE_TYPES = (
    "confused_model",
    "keyword_missing",
    "business_scenario_mismatch",
    "semantic_similar_but_wrong",
    "metadata_gap",
    "unknown",
)

# ─── Helpers ────────────────────────────────────────────────────────


def _build_model_text(model: dict[str, Any]) -> str:
    """Replicate OfficialRecommender._get_model_text for token extraction."""
    parts: list[str] = [
        model.get("model_name", ""),
        model.get("description", ""),
        model.get("business_scenario", ""),
    ]
    tags = model.get("tags", [])
    if isinstance(tags, list):
        parts.extend(tags)
    return " ".join(str(p) for p in parts if p)


def classify_failure(
    query: str,
    gold_model_ids: list[str],
    recs: list[dict[str, Any]],
    top1_hit: bool,
    top3_hit: bool,
    top5_hit: bool,
    recommender: OfficialRecommender,
) -> str | None:
    """
    Classify failure type using the priority chain described in 4.5.

    Priority:
      1. confused_model
      2. keyword_missing
      3. business_scenario_mismatch
      4. semantic_similar_but_wrong
      5. metadata_gap
      6. unknown

    Returns None when top1_hit is True (perfect match).
    """
    # ── Perfect match ──────────────────────────────────────────
    if top1_hit:
        return None

    # ── Confused Model (Case A): gold in positions 2-5 ─────────
    if top5_hit:
        return "confused_model"

    # ── From here, top5_hit == False ────────────────────────────
    gold_id = gold_model_ids[0] if gold_model_ids else None
    gold_m: dict | None = recommender.model_by_id.get(gold_id) if gold_id else None
    if not gold_m or not recs:
        return "unknown"

    top1_m: dict | None = recommender.model_by_id.get(recs[0]["model_id"]) if recs else None

    # 1. Confused Model (Case B): same domain + significant name overlap
    if top1_m and gold_m:
        gold_domain = gold_m.get("domain", "")
        top1_domain = top1_m.get("domain", "")
        gold_name_tokens = recommender._extract_tokens(gold_m.get("model_name", ""))
        top1_name_tokens = recommender._extract_tokens(top1_m.get("model_name", ""))
        name_overlap = len(gold_name_tokens & top1_name_tokens)
        if gold_domain == top1_domain and name_overlap >= 3:
            return "confused_model"

    # 2. Keyword Missing
    query_tokens = recommender._extract_tokens(query)
    gold_text = _build_model_text(gold_m)
    gold_tokens = recommender._extract_tokens(gold_text)
    if len(query_tokens & gold_tokens) <= 1:
        return "keyword_missing"

    # 3. Business Scenario Mismatch
    if top1_m and gold_m:
        gold_scenario_tokens = recommender._extract_tokens(
            gold_m.get("business_scenario", "")
        )
        top1_scenario_tokens = recommender._extract_tokens(
            top1_m.get("business_scenario", "")
        )
        q_gold_scenario = len(query_tokens & gold_scenario_tokens)
        q_top1_scenario = len(query_tokens & top1_scenario_tokens)
        if q_gold_scenario <= 1 and q_top1_scenario >= 2:
            return "business_scenario_mismatch"

    # 4. Semantic Similar But Wrong
    if top1_m and gold_m:
        gold_name_tokens = recommender._extract_tokens(gold_m.get("model_name", ""))
        top1_name_tokens = recommender._extract_tokens(top1_m.get("model_name", ""))
        name_overlap = len(gold_name_tokens & top1_name_tokens)
        if top1_m["model_id"] != gold_id and name_overlap >= 2:
            return "semantic_similar_but_wrong"

    # 5. Metadata Gap
    desc = gold_m.get("description", "")
    tags = gold_m.get("tags", [])
    if len(desc) < 20 or len(tags) <= 3:
        return "metadata_gap"

    return "unknown"


def enrich_failure(
    r: dict[str, Any],
    recommender: OfficialRecommender,
) -> dict[str, Any]:
    """
    Enrich a failure record with failure_scope, reason, and suggested_fix.

    Called for every result where top1_hit == False.
    """
    result = dict(r)  # shallow copy

    # ── Determine failure scope ──────────────────────────────
    top1_hit = r["top1_hit"]
    top3_hit = r["top3_hit"]
    top5_hit = r["top5_hit"]

    if not top5_hit:
        result["failure_scope"] = "top5_miss"
    elif not top3_hit:
        result["failure_scope"] = "top3_miss"
    elif not top1_hit:
        result["failure_scope"] = "top1_miss"
    else:
        result["failure_scope"] = "unknown"

    # ── Helper info ──────────────────────────────────────────
    gold_id = r["gold_model_ids"][0] if r["gold_model_ids"] else None
    gold_name = r["gold_model_names"][0] if r["gold_model_names"] else "?"

    rank: int | None = None
    if gold_id and r["recommended_top5"]:
        try:
            rank = r["recommended_top5"].index(gold_id) + 1
        except ValueError:
            rank = None

    top1_model = r["recommended_models"][0] if r["recommended_models"] else None
    top1_name = top1_model.get("model_name", "?") if top1_model else "?"
    top1_id = r["recommended_top5"][0] if r["recommended_top5"] else "?"

    query = r["query"]
    ft = r.get("failure_type", "unknown")
    scope = result["failure_scope"]

    # ── Reason ───────────────────────────────────────────────
    reason_parts: list[str] = []

    if scope == "top5_miss":
        reason_parts.append(
            f"Gold model '{gold_name}' ({gold_id}) not in top5."
        )
    elif scope == "top3_miss" and rank is not None:
        reason_parts.append(
            f"Gold model '{gold_name}' ({gold_id}) appears at rank "
            f"{rank} (outside top3)."
        )
    elif scope == "top1_miss" and rank is not None:
        reason_parts.append(
            f"Gold model '{gold_name}' ({gold_id}) appears at rank "
            f"{rank} (not top1)."
        )

    if ft == "confused_model":
        if top1_model:
            gold_m = recommender.model_by_id.get(gold_id) if gold_id else None
            domain_info = ""
            if gold_m and top1_model:
                gold_domain = gold_m.get("domain", "")
                t1_domain = top1_model.get("domain", "")
                if gold_domain == t1_domain:
                    domain_info = f" shares domain '{gold_domain}'"
            g_name_tokens = recommender._extract_tokens(gold_name)
            t1_name_tokens = recommender._extract_tokens(top1_name)
            name_overlap = len(g_name_tokens & t1_name_tokens)
            reason_parts.append(
                f"Top1 '{top1_name}' ({top1_id}){domain_info} "
                f"and {name_overlap} name keyword(s) overlap."
            )
        else:
            reason_parts.append("No valid top1 recommendation.")
    elif ft == "keyword_missing":
        reason_parts.append(
            f"Query '{query}' shares few keyword tokens with "
            f"gold model description/tags."
        )
    elif ft == "business_scenario_mismatch":
        reason_parts.append(
            f"Query '{query}' better matches top1 scenario than "
            f"gold model scenario."
        )
    elif ft == "semantic_similar_but_wrong":
        reason_parts.append(
            f"Top1 '{top1_name}' has semantically similar name "
            f"to gold model."
        )
    elif ft == "metadata_gap":
        reason_parts.append(
            f"Gold model '{gold_name}' has sparse description or "
            f"few tags."
        )
    else:
        reason_parts.append("Root cause not clearly identified.")

    result["reason"] = " ".join(reason_parts)

    # ── Suggested fix ────────────────────────────────────────
    if scope == "top1_miss" and ft == "confused_model":
        result["suggested_fix"] = (
            "Improve inter-class discrimination by weighting "
            "description/scenario matches higher than name matches."
        )
    elif scope == "top3_miss":
        result["suggested_fix"] = (
            "Strengthen mid-rank signals or expand synonyms for "
            "key query terms."
        )
    elif scope == "top5_miss" and ft == "keyword_missing":
        result["suggested_fix"] = (
            "Add domain-specific synonyms to data/config/synonyms.json."
        )
    elif scope == "top5_miss" and ft == "business_scenario_mismatch":
        result["suggested_fix"] = (
            "Add scenario-level synonym group or scenario-matching bonus."
        )
    elif scope == "top5_miss" and ft == "confused_model":
        result["suggested_fix"] = (
            "Improve inter-class discrimination by weighting "
            "description/scenario matches higher than name matches."
        )
    else:
        result["suggested_fix"] = (
            "Review model metadata and query intent alignment; "
            "consider adding more distinguishing features to "
            "model entries."
        )

    return result


def load_queries(path: Path) -> list[dict[str, Any]]:
    """Load JSONL query file into a list of dicts."""
    queries: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


def evaluate_split(
    recommender: OfficialRecommender,
    queries: list[dict[str, Any]],
    split_name: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Evaluate the recommender on a set of queries.

    Returns (results_list, summary_dict).
    """
    results: list[dict[str, Any]] = []
    top1 = top3 = top5 = 0
    total = len(queries)

    for q in queries:
        qid: str = q["query_id"]
        query_text: str = q["query"]
        gold_ids: list[str] = q["gold_model_ids"]
        gold_names: list[str] = q["gold_model_names"]

        recs = recommender.recommend(query_text, top_k=5)
        rec_ids = [r["model_id"] for r in recs]

        top1_hit = bool(rec_ids) and any(g == rec_ids[0] for g in gold_ids)
        top3_hit = bool(rec_ids) and any(g in rec_ids[:3] for g in gold_ids)
        top5_hit = bool(rec_ids) and any(g in rec_ids for g in gold_ids)

        if top1_hit:
            top1 += 1
        if top3_hit:
            top3 += 1
        if top5_hit:
            top5 += 1

        failure = classify_failure(
            query_text, gold_ids, recs, top1_hit, top3_hit, top5_hit, recommender
        )

        results.append({
            "query_id": qid,
            "split": split_name,
            "query": query_text,
            "gold_model_ids": gold_ids,
            "gold_model_names": gold_names,
            "recommended_top5": rec_ids,
            "recommended_models": recs,
            "top1_hit": top1_hit,
            "top3_hit": top3_hit,
            "top5_hit": top5_hit,
            "failure_type": failure,
        })

    def _rate(hits: int) -> float:
        return round(hits / total * 100, 1) if total else 0.0

    summary: dict[str, Any] = {
        "total": total,
        "top1_hits": top1,
        "top3_hits": top3,
        "top5_hits": top5,
        "top1_rate": _rate(top1),
        "top3_rate": _rate(top3),
        "top5_rate": _rate(top5),
    }
    return results, summary


def count_failures(results: list[dict[str, Any]]) -> dict[str, int]:
    """Count occurrences of each failure type among results."""
    counter: Counter[str] = Counter()
    for r in results:
        ft = r.get("failure_type")
        if ft:
            counter[ft] += 1
    # Ensure all known types appear even if zero
    out = {ft: counter.get(ft, 0) for ft in _FAILURE_TYPES}
    return out


def pick_failure_samples(
    results: list[dict[str, Any]], max_per_type: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Pick representative failure samples for each failure type."""
    samples: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        ft = r.get("failure_type")
        if ft and ft not in samples:
            samples[ft] = []
        if ft and len(samples[ft]) < max_per_type:
            samples[ft].append(r)
    return samples


def build_markdown_report(
    val_summary: dict[str, Any],
    test_summary: dict[str, Any],
    val_failures: dict[str, int],
    test_failures: dict[str, int],
    total_failures: dict[str, int],
    failure_samples: dict[str, list[dict[str, Any]]],
    now_str: str,
) -> str:
    """Generate the markdown evaluation report."""
    val_misses = val_summary["total"] - val_summary["top5_hits"]
    test_misses = test_summary["total"] - test_summary["top5_hits"]

    lines: list[str] = []
    _a = lines.append

    _a("# Official Recommender Top-K Evaluation Report")
    _a(f"**Generated:** {now_str}")
    _a("")
    _a("## 1. Val Set Results")
    _a(f"- **Total queries:** {val_summary['total']}")
    _a(f"- **Top1 hits:** {val_summary['top1_hits']}  ({val_summary['top1_rate']}%)")
    _a(f"- **Top3 hits:** {val_summary['top3_hits']}  ({val_summary['top3_rate']}%)")
    _a(f"- **Top5 hits:** {val_summary['top5_hits']}  ({val_summary['top5_rate']}%)")
    _a(f"- **Misses (not in Top5):** {val_misses}")
    _a("")

    _a("## 2. Test Set Results")
    _a(f"- **Total queries:** {test_summary['total']}")
    _a(f"- **Top1 hits:** {test_summary['top1_hits']}  ({test_summary['top1_rate']}%)")
    _a(f"- **Top3 hits:** {test_summary['top3_hits']}  ({test_summary['top3_rate']}%)")
    _a(f"- **Top5 hits:** {test_summary['top5_hits']}  ({test_summary['top5_rate']}%)")
    _a(f"- **Misses (not in Top5):** {test_misses}")
    _a("")

    _a("## 3. Summary")
    _a("")
    _a("| Metric | Val | Test |")
    _a("|--------|----:|-----:|")
    _a(f"| Total       | {val_summary['total']:>3d} | {test_summary['total']:>3d} |")
    _a(f"| Top1 Rate   | {val_summary['top1_rate']:>5.1f}% | {test_summary['top1_rate']:>5.1f}% |")
    _a(f"| Top3 Rate   | {val_summary['top3_rate']:>5.1f}% | {test_summary['top3_rate']:>5.1f}% |")
    _a(f"| Top5 Rate   | {val_summary['top5_rate']:>5.1f}% | {test_summary['top5_rate']:>5.1f}% |")
    _a(f"| Misses      | {val_misses:>3d} | {test_misses:>3d} |")
    _a("")

    _a("## 4. Failure Attribution")
    _a("")
    _a("| Failure Type | Val | Test | Total |")
    _a("|--------------|----:|-----:|------:|")
    for ft in _FAILURE_TYPES:
        _a(
            f"| {ft} | {val_failures.get(ft, 0):>3d} | "
            f"{test_failures.get(ft, 0):>3d} | {total_failures.get(ft, 0):>3d} |"
        )
    _a("")

    _a("## 5. Typical Failure Samples")
    _a("")
    for ft in _FAILURE_TYPES:
        samples = failure_samples.get(ft, [])
        if not samples:
            _a(f"### {ft}")
            _a("No samples.")
            _a("")
            continue
        _a(f"### {ft}")
        _a("")
        for i, s in enumerate(samples, 1):
            _a(f"**Example {i}**")
            _a(f"- Query: `{s['query']}`")
            _a(f"- Gold: `{s['gold_model_names'][0]}` ({s['gold_model_ids'][0]})")
            _a(f"- Top5: `{'`, `'.join(s['recommended_top5'])}`")
            _a(f"- Failure type: `{s['failure_type']}` | Scope: `{s.get('failure_scope', '?')}`")
            if s.get("reason"):
                _a(f"- Reason: {s['reason']}")
            if s.get("suggested_fix"):
                _a(f"- Suggested fix: {s['suggested_fix']}")
            _a("")
            if s.get("recommended_models"):
                top1_name = s["recommended_models"][0].get("model_name", "?")
                top1_id = s["recommended_models"][0]["model_id"]
                _a(f"  - Top1 model: `{top1_name}` ({top1_id})")
                _a("")

    _a("## 6. Improvement Suggestions")
    _a("")

    # Generate suggestions based on failure distribution
    suggestions: list[str] = []

    kw_missing = total_failures.get("keyword_missing", 0)
    confused = total_failures.get("confused_model", 0)
    business_mismatch = total_failures.get("business_scenario_mismatch", 0)
    semantic = total_failures.get("semantic_similar_but_wrong", 0)
    meta_gap = total_failures.get("metadata_gap", 0)

    if kw_missing > 0:
        suggestions.append(
            f"**Expand synonym coverage.** "
            f"`keyword_missing` accounts for {kw_missing} failures. "
            "Add domain-specific synonyms and key phrases from the gold model "
            "descriptions (e.g., '促提', '回捞', '拓客') to the synonym map."
        )
    if confused > 0:
        suggestions.append(
            f"**Improve inter-class discrimination.** "
            f"`confused_model` accounts for {confused} failures. "
            "When multiple models share domain and name keywords, the scorer "
            "needs additional signals (e.g., weighting description/scenario "
            "matches higher than name matches) to differentiate them."
        )
    if business_mismatch > 0:
        suggestions.append(
            f"**Boost business-scenario signals.** "
            f"`business_scenario_mismatch` accounts for {business_mismatch} failures. "
            "Consider adding a dedicated scenario-matching bonus or a "
            "scenario-level synonym group to align query intent with "
            "business scenario labels."
        )
    if semantic > 0:
        suggestions.append(
            f"**Handle semantically similar model names.** "
            f"`semantic_similar_but_wrong` accounts for {semantic} failures. "
            "When model names share multiple bigrams (e.g., both contain "
            "'违约概率'), the scorer should penalize non-exact name matches "
            "or prefer models whose description keywords better align with "
            "the query."
        )
    if meta_gap > 0:
        suggestions.append(
            f"**Enrich metadata for sparse models.** "
            f"`metadata_gap` accounts for {meta_gap} failures. "
            "Models with very short descriptions or few tags are hard to match. "
            "Fill missing description / tags for these models in the dataset."
        )

    # Fallback
    if not suggestions:
        suggestions.append(
            "Consider continuous evaluation as new models or queries are added "
            "to the dataset."
        )

    for idx, sug in enumerate(suggestions, 1):
        _a(f"{idx}. {sug}")
        _a("")

    _a("---")
    _a(f"_Report generated by `scripts/evaluate_official_topk.py` at {now_str}_")

    return "\n".join(lines)


# ─── Main ───────────────────────────────────────────────────────────


def main() -> None:
    recommender = OfficialRecommender()

    # Load queries
    val_queries = load_queries(DATA_DIR / "queries_val.jsonl")
    test_queries = load_queries(DATA_DIR / "queries_test.jsonl")

    print(f"Loaded {len(val_queries)} val queries, {len(test_queries)} test queries.")

    # Evaluate
    val_results, val_summary = evaluate_split(recommender, val_queries, "val")
    test_results, test_summary = evaluate_split(recommender, test_queries, "test")

    # Count failures
    val_failures = count_failures(val_results)
    test_failures = count_failures(test_results)
    all_types = sorted(
        set(list(val_failures.keys()) + list(test_failures.keys()))
    )
    total_failures = {
        k: val_failures.get(k, 0) + test_failures.get(k, 0) for k in all_types
    }

    # Collect all failure cases (top1_hit == false) with enriched analysis
    failure_cases: list[dict[str, Any]] = []
    for r in val_results + test_results:
        if not r["top1_hit"]:
            failure_cases.append(enrich_failure(r, recommender))

    # Pick samples for markdown report (from enriched failure_cases)
    failure_samples = pick_failure_samples(failure_cases, max_per_type=2)

    # Timestamp
    now_str = datetime.now().isoformat()

    # Preserve other evidence stored beside these generated Top-K reports.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. official_topk_summary.json ──────────────────────────
    summary: dict[str, Any] = {
        "generated_at": now_str,
        "source": {
            "models": "data/official_60/models.jsonl",
            "val_queries": "data/official_60/queries_val.jsonl",
            "test_queries": "data/official_60/queries_test.jsonl",
        },
        "top1_accuracy": val_summary["top1_rate"],
        "top3_accuracy": val_summary["top3_rate"],
        "top5_accuracy": val_summary["top5_rate"],
        "val": val_summary,
        "test": test_summary,
        "failure_attribution": {
            "val": val_failures,
            "test": test_failures,
            "total": total_failures,
        },
    }
    with open(REPORTS_DIR / "official_topk_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("[OK] official_topk_summary.json")

    # ── 2. val_results.json ───────────────────────────────────
    val_package: dict[str, Any] = {
        "split": "val",
        **val_summary,
        "results": val_results,
    }
    with open(REPORTS_DIR / "val_results.json", "w", encoding="utf-8") as f:
        json.dump(val_package, f, ensure_ascii=False, indent=2)
    print("[OK] val_results.json")

    # ── 3. test_results.json ──────────────────────────────────
    test_package: dict[str, Any] = {
        "split": "test",
        **test_summary,
        "results": test_results,
    }
    with open(REPORTS_DIR / "test_results.json", "w", encoding="utf-8") as f:
        json.dump(test_package, f, ensure_ascii=False, indent=2)
    print("[OK] test_results.json")

    # ── 4. official_failures.json ─────────────────────────────
    with open(REPORTS_DIR / "official_failures.json", "w", encoding="utf-8") as f:
        json.dump(failure_cases, f, ensure_ascii=False, indent=2)
    print("[OK] official_failures.json")

    # ── 5. official_topk_report.md ───────────────────────────
    report_md = build_markdown_report(
        val_summary,
        test_summary,
        val_failures,
        test_failures,
        total_failures,
        failure_samples,
        now_str,
    )
    with open(REPORTS_DIR / "official_topk_report.md", "w", encoding="utf-8") as f:
        f.write(report_md)
    print("[OK] official_topk_report.md")

    # ── Console summary ──────────────────────────────────────
    val_misses = val_summary["total"] - val_summary["top5_hits"]
    test_misses = test_summary["total"] - test_summary["top5_hits"]

    print()
    print("=" * 66)
    print("  Official Recommender Top-K Evaluation")
    print("=" * 66)
    print(
        f"  Val  ({val_summary['total']:>2d} q):  "
        f"Top1={val_summary['top1_rate']:>5.1f}%  "
        f"Top3={val_summary['top3_rate']:>5.1f}%  "
        f"Top5={val_summary['top5_rate']:>5.1f}%  "
        f"Miss={val_misses:>2d}"
    )
    print(
        f"  Test ({test_summary['total']:>2d} q):  "
        f"Top1={test_summary['top1_rate']:>5.1f}%  "
        f"Top3={test_summary['top3_rate']:>5.1f}%  "
        f"Top5={test_summary['top5_rate']:>5.1f}%  "
        f"Miss={test_misses:>2d}"
    )
    print("  Failure attribution (val | test | total):")
    for ft in _FAILURE_TYPES:
        v = val_failures.get(ft, 0)
        t = test_failures.get(ft, 0)
        tt = total_failures.get(ft, 0)
        if v or t or tt:
            print(f"    {ft:>32s}:  {v:>3d} | {t:>3d} | {tt:>3d}")
    # Failure scope distribution
    scope_counts: Counter[str] = Counter()
    for fc in failure_cases:
        scope_counts[fc.get("failure_scope", "unknown")] += 1
    if scope_counts:
        print("  Failure scope distribution:")
        for sc in ("top5_miss", "top3_miss", "top1_miss"):
            cnt = scope_counts.get(sc, 0)
            if cnt:
                print(f"    {sc:>13s}: {cnt:>3d}")
    print("=" * 66)
    print(f"  Report directory: {REPORTS_DIR}")
    print("=" * 66)


if __name__ == "__main__":
    main()
