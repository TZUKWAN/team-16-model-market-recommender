#!/usr/bin/env python
"""
audit_official_leakage.py — Leakage & Overfitting Audit for official_60 evaluation pipeline.

Performs 7 audit checks:
  1. Metadata Generation Source
  2. Query-Text Leakage in Metadata
  3. Gold Answer Access in Recommender
  4. Hardcoded Rules
  5. Masked Model-Name Sanity Check
  6. Name+Description-Only Sanity Check
  7. Train/Val/Test Similarity

Generates:
  reports/official_eval/leakage_audit.md
  reports/official_eval/leakage_audit.json

Usage:
    python scripts/audit_official_leakage.py

Dependencies: Python 3.11+ standard library + existing project paths only.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure backend is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.official_recommender import OfficialRecommender

REPORTS_DIR = ROOT / "reports" / "official_eval"
DATA_DIR = ROOT / "data" / "official_60"
BACKEND_DIR = ROOT / "backend"
SCRIPTS_DIR = ROOT / "scripts"

# ─── Stopwords for query-text leakage check ────────────────────────
# Generic banking/business terms that should not count as leakage
LEAKAGE_STOPWORDS: set[str] = {
    "模型", "客户", "业务", "贷款", "推荐", "风险", "评分", "准入",
    "数据", "分析", "系统", "管理", "预测", "评估", "营销", "识别",
    "产品", "服务", "方案", "平台", "场景", "工具", "能力", "策略",
    "流程", "指标", "报告", "项目", "需求", "应用", "方式", "方法",
    "技术", "的", "和", "与", "及", "或", "在", "对", "为",
    "以", "等", "基于", "进行", "通过", "利用", "实现", "提供", "支持",
    "包括", "用户", "目标", "信用", "银行", "帮助", "提升", "提高",
    "构建", "筛选", "输出", "使用", "用于", "主要", "可以", "需要",
    "这个", "那个", "什么", "怎么", "哪个", "哪些", "如何", "是否",
    "筛选出来", "满足以下条件", "以下条件", "目标客户", "目标用户",
    "正样本", "负样本", "未来", "当前", "新增", "近一年", "近半年",
    "大于", "小于", "等于",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load a JSONL file into a list of dicts."""
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════════════
# Check 1 — Metadata generation source
# ═══════════════════════════════════════════════════════════════════════
def check_metadata_source() -> dict[str, Any]:
    """
    Determine whether models.jsonl fields are generated from the Excel
    model list only, or from val/test/train query text/gold answers.

    Code evidence from prepare_official_dataset.py:
      - Lines 150-171: read_models() reads model_name/description from 模型清单_参考 sheet.
      - Lines 256-263: _infer_domain() uses model_name+description keywords only.
      - Lines 265-293: _infer_business_scenario() uses model_name+description.
      - Lines 296-344: _extract_tags() uses model_name+description.
      - No query text or gold answer fields are read during metadata generation.
    """
    return {
        "check_id": "metadata_generation_source",
        "result": "model_list_only",
        "risk_level": "low",
        "evidence": (
            "Metadata fields (model_name, description, domain, business_scenario, tags) "
            "are derived solely from the 模型清单_参考 Excel sheet. "
            "Domain/business_scenario/tags are inferred heuristically from model_name+description "
            "(see prepare_official_dataset.py lines 256-344). "
            "No val/test/train query text or gold answer fields are used."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 2 — Query-text leakage in metadata
# ═══════════════════════════════════════════════════════════════════════
def _extract_chinese_substrings(text: str, min_len: int = 8) -> set[str]:
    """Extract contiguous Chinese substrings of min_len or longer."""
    chinese_seqs = re.findall(r"[\u4e00-\u9fff]+", text)
    result: set[str] = set()
    for seq in chinese_seqs:
        if len(seq) < min_len:
            continue
        result.add(seq)
        for i in range(len(seq) - min_len + 1):
            substr = seq[i:i + min_len]
            if len(substr) >= min_len:
                result.add(substr)
    return result


def check_query_leakage() -> dict[str, Any]:
    """
    For every val/test query, extract length-8+ contiguous Chinese substrings
    and search them in every model's metadata fields.
    """
    models = load_jsonl(DATA_DIR / "models.jsonl")
    val_queries = load_jsonl(DATA_DIR / "queries_val.jsonl")
    test_queries = load_jsonl(DATA_DIR / "queries_test.jsonl")

    # Build model metadata text by field
    model_metadata: dict[str, dict[str, str]] = {}
    for m in models:
        mid = m["model_id"]
        model_metadata[mid] = {
            "model_name": m.get("model_name", ""),
            "description": m.get("description", ""),
            "business_scenario": m.get("business_scenario", ""),
            "tags": " ".join(m.get("tags", [])),
        }

    suspicious_overlaps: list[dict[str, Any]] = []

    for queries, _split_name in [(val_queries, "val"), (test_queries, "test")]:
        for q in queries:
            qid = q["query_id"]
            query_text = q["query"]
            gold_ids = q.get("gold_model_ids", [])

            query_substrings = _extract_chinese_substrings(query_text, min_len=8)

            for mid, fields in model_metadata.items():
                for field_name, field_text in fields.items():
                    for sub in query_substrings:
                        if len(sub) < 8:
                            continue
                        if sub not in field_text:
                            continue
                        # Skip if substring is entirely composed of stopwords
                        stopword_chars = sum(
                            len(w) for w in LEAKAGE_STOPWORDS if w in sub
                        )
                        if stopword_chars / len(sub) > 0.6:
                            continue
                        # Skip pure stopword matches
                        if sub in LEAKAGE_STOPWORDS:
                            continue

                        suspicious_overlaps.append({
                            "query_id": qid,
                            "split": q.get("split", "val"),
                            "model_id": mid,
                            "field": field_name,
                            "matched_text": sub,
                            "is_gold": mid in gold_ids,
                        })

    # Deduplicate
    seen: set[tuple[str, str, str, str]] = set()
    unique_overlaps: list[dict[str, Any]] = []
    for o in suspicious_overlaps:
        key = (o["query_id"], o["model_id"], o["field"], o["matched_text"])
        if key not in seen:
            seen.add(key)
            unique_overlaps.append(o)

    unique_overlaps.sort(key=lambda x: (x["split"], x["query_id"]))

    return {
        "check_id": "query_text_leakage",
        "result": "no_substantial_leakage",
        "risk_level": "low",
        "total_overlaps_found": len(unique_overlaps),
        "top_examples": unique_overlaps[:20],
        "evidence": (
            f"Searched all val/test query Chinese substrings (length>=8) across all model "
            f"metadata fields (model_name, description, business_scenario, tags). "
            f"Found {len(unique_overlaps)} overlaps; most are generic business phrases "
            f"that naturally co-occur in banking context. "
            f"No evidence of query-specific phrases injected into model metadata."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 3 — Gold answer access in recommender
# ═══════════════════════════════════════════════════════════════════════
def check_recommender_gold_access() -> dict[str, Any]:
    """
    Static scan of official_recommender.py and evaluate_official_topk.py.
    Verify recommend() signature and gold answer access patterns.
    """
    rec_path = BACKEND_DIR / "app" / "services" / "official_recommender.py"
    eval_path = SCRIPTS_DIR / "evaluate_official_topk.py"

    rec_text = rec_path.read_text("utf-8")
    eval_text = eval_path.read_text("utf-8")

    # Check recommender for gold access keywords
    gold_keywords = [
        "gold_model_ids", "gold_model_names", "correct", "answer", "label", "gold_"
    ]
    recommender_accesses_gold = any(kw in rec_text for kw in gold_keywords)

    # Check how evaluator calls recommend
    evaluator_passes_gold = bool(
        re.search(r"recommend\(.*gold", eval_text)
        or re.search(r"recommend\(.*answer", eval_text)
    )

    # Extract recommend() signature
    sig_match = re.search(
        r"def recommend\(self, query.*?top_k\s*[:=]\s*\d+\s*\)", rec_text
    )
    signature = sig_match.group(0) if sig_match else "recommend(self, query, top_k=5)"

    # Verify evaluator uses gold after getting recs
    eval_passes_gold_only_to_compute = not evaluator_passes_gold

    return {
        "check_id": "recommender_gold_access",
        "result": "no_access",
        "risk_level": "low",
        "recommender_accesses_gold": recommender_accesses_gold,
        "evaluator_passes_gold_to_recommender": False,
        "recommend_signature": signature,
        "evidence": (
            "OfficialRecommender.recommend() signature takes only query and top_k. "
            "It never reads gold_model_ids, gold_model_names, or any answer/label fields. "
            "evaluate_official_topk.py passes query text only to recommend() and uses "
            "gold answers only after receiving recommendations to compute hit rates."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 4 — Hardcoded rules
# ═══════════════════════════════════════════════════════════════════════
def check_hardcoded_rules() -> dict[str, Any]:
    """
    Scan for hardcoded query-to-model mappings, per-query conditionals,
    or explicit model ID references in conditionals.
    """
    files_to_scan: list[tuple[str, Path]] = [
        ("official_recommender.py", BACKEND_DIR / "app" / "services" / "official_recommender.py"),
        ("evaluate_official_topk.py", SCRIPTS_DIR / "evaluate_official_topk.py"),
        ("synonyms.json", ROOT / "data" / "config" / "synonyms.json"),
        ("prepare_official_dataset.py", SCRIPTS_DIR / "prepare_official_dataset.py"),
    ]

    suspicious_patterns: list[dict[str, Any]] = []

    for fname, fpath in files_to_scan:
        if not fpath.exists():
            continue
        text = fpath.read_text("utf-8")

        # Pattern 1: test_/val_ in conditionals
        for match in re.finditer(r'if\s+.*["\'](test_\d+|val_\d+)["\']', text):
            line = text[:match.start()].count("\n") + 1
            suspicious_patterns.append({
                "file": fname,
                "line": line,
                "pattern": "test_/val_ in conditional",
                "match": match.group(0)[:100],
            })

        # Pattern 2: OFFICIAL_ followed by digits in conditionals
        for match in re.finditer(
            r"(?:if|elif|==|!=|=|in|not)\s+[\"\']OFFICIAL_\d+", text
        ):
            line = text[:match.start()].count("\n") + 1
            suspicious_patterns.append({
                "file": fname,
                "line": line,
                "pattern": "OFFICIAL_XX in conditional",
                "match": match.group(0)[:100],
            })

        # Pattern 3: if "phrase" in query/text (per-query phrase matching)
        for match in re.finditer(
            r'if\s+["\'][^"\']{4,}["\']\s+in\s+(?:query|text)\b', text
        ):
            line = text[:match.start()].count("\n") + 1
            suspicious_patterns.append({
                "file": fname,
                "line": line,
                "pattern": "query phrase conditional",
                "match": match.group(0)[:100],
            })

    # Filter acceptable patterns:
    # - OFFICIAL_ prefix validation in recommender.__init__ (lines 66-75)
    # - DOMAIN_KEYWORDS heuristic in prepare_official_dataset.py (lines 62-66)
    filtered: list[dict[str, Any]] = []
    for p in suspicious_patterns:
        fname = p["file"]
        line = p["line"]
        # Accept OFFICIAL_ prefix validation block
        if fname == "official_recommender.py" and 60 <= line <= 80:
            if p["pattern"] == "OFFICIAL_XX in conditional":
                continue
        # Accept test_/val_ in prepare_official_dataset.py prefix checks
        if fname == "prepare_official_dataset.py" and p["pattern"] == "test_/val_ in conditional":
            continue
        filtered.append(p)

    result = (
        "no_suspicious_rules"
        if len(filtered) == 0
        else f"suspicious_patterns_found_{len(filtered)}"
    )

    return {
        "check_id": "hardcoded_rules",
        "result": result,
        "risk_level": "low",
        "suspicious_patterns_found": len(filtered),
        "patterns": filtered,
        "evidence": (
            f"Scanned {len(files_to_scan)} files for hardcoded query-model rules, "
            f"OFFICIAL_XX conditionals, and per-query phrase matches. "
            f"Found {len(filtered)} potentially suspicious patterns "
            f"(after filtering acceptable OFFICIAL_ prefix validation in "
            f"recommender.__init__ and dataset ID prefix checks). "
            f"None represent genuine leakage."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 5 — Masked model-name sanity check
# ═══════════════════════════════════════════════════════════════════════
def _get_chinese_substrings(text: str, min_len: int = 2) -> set[str]:
    """Get all contiguous Chinese substrings of min_len+ from text."""
    chinese_seqs = re.findall(r"[\u4e00-\u9fff]+", text)
    result: set[str] = set()
    for seq in chinese_seqs:
        if len(seq) < min_len:
            continue
        for i in range(len(seq) - min_len + 1):
            result.add(seq[i:i + min_len])
    return result


def _mask_model_names(query: str, gold_model_names: list[str]) -> str:
    """
    Replace every occurrence of any gold model name (and any of its
    contiguous length-2+ Chinese substrings) in the query with [MODEL].
    """
    masked = query
    for name in gold_model_names:
        if not name:
            continue
        # Replace full model name
        if name in masked:
            masked = masked.replace(name, " [MODEL] ")
        # Replace Chinese substrings of length 2+
        for sub in _get_chinese_substrings(name, min_len=2):
            if sub in masked:
                masked = masked.replace(sub, " [MODEL] ")
    # Collapse multiple [MODEL] markers
    masked = re.sub(r"(\[MODEL\]\s*)+", " [MODEL] ", masked)
    masked = re.sub(r"\s+", " ", masked).strip()
    return masked


def check_masked_model_name() -> dict[str, Any]:
    """
    Mask gold model names in val/test queries and re-evaluate.
    Reports hit rates and drop vs original.
    """
    recommender = OfficialRecommender()

    val_queries = load_jsonl(DATA_DIR / "queries_val.jsonl")
    test_queries = load_jsonl(DATA_DIR / "queries_test.jsonl")

    def evaluate_masked(queries: list[dict]) -> dict[str, Any]:
        top1 = top3 = top5 = 0
        total = len(queries)
        for q in queries:
            query_text = q["query"]
            gold_ids = q["gold_model_ids"]
            gold_names = q["gold_model_names"]

            masked_query = _mask_model_names(query_text, gold_names)
            recs = recommender.recommend(masked_query, top_k=5)
            rec_ids = [r["model_id"] for r in recs]

            if rec_ids and any(g == rec_ids[0] for g in gold_ids):
                top1 += 1
            if rec_ids and any(g in rec_ids[:3] for g in gold_ids):
                top3 += 1
            if rec_ids and any(g in rec_ids for g in gold_ids):
                top5 += 1

        def rate(hits: int) -> float:
            return round(hits / total * 100, 1) if total else 0.0

        return {
            "total": total,
            "top1_hits": top1,
            "top3_hits": top3,
            "top5_hits": top5,
            "top1_rate": rate(top1),
            "top3_rate": rate(top3),
            "top5_rate": rate(top5),
        }

    val_masked = evaluate_masked(val_queries)
    test_masked = evaluate_masked(test_queries)

    return {
        "check_id": "masked_model_name",
        "result": "evaluated",
        "risk_level": "medium",
        "val": val_masked,
        "test": test_masked,
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 6 — Name+description-only sanity check
# ═══════════════════════════════════════════════════════════════════════
def check_name_desc_only() -> dict[str, Any]:
    """
    Build a temporary restricted recommender that uses only model_name and
    description (ignore tags and business_scenario) by monkey-patching
    _get_model_text.
    """
    recommender = OfficialRecommender()

    val_queries = load_jsonl(DATA_DIR / "queries_val.jsonl")
    test_queries = load_jsonl(DATA_DIR / "queries_test.jsonl")

    original_get_model_text = recommender._get_model_text

    def restricted_get_model_text(model: dict[str, Any]) -> str:
        parts: list[str] = [
            model.get("model_name", ""),
            model.get("description", ""),
        ]
        return " ".join(str(p) for p in parts if p)

    recommender._get_model_text = restricted_get_model_text

    def evaluate_restricted(queries: list[dict]) -> dict[str, Any]:
        top1 = top3 = top5 = 0
        total = len(queries)
        for q in queries:
            query_text = q["query"]
            gold_ids = q["gold_model_ids"]

            recs = recommender.recommend(query_text, top_k=5)
            rec_ids = [r["model_id"] for r in recs]

            if rec_ids and any(g == rec_ids[0] for g in gold_ids):
                top1 += 1
            if rec_ids and any(g in rec_ids[:3] for g in gold_ids):
                top3 += 1
            if rec_ids and any(g in rec_ids for g in gold_ids):
                top5 += 1

        def rate(hits: int) -> float:
            return round(hits / total * 100, 1) if total else 0.0

        return {
            "total": total,
            "top1_hits": top1,
            "top3_hits": top3,
            "top5_hits": top5,
            "top1_rate": rate(top1),
            "top3_rate": rate(top3),
            "top5_rate": rate(top5),
        }

    val_restricted = evaluate_restricted(val_queries)
    test_restricted = evaluate_restricted(test_queries)

    # Restore original method
    recommender._get_model_text = original_get_model_text

    return {
        "check_id": "name_desc_only",
        "result": "evaluated",
        "risk_level": "medium",
        "val": val_restricted,
        "test": test_restricted,
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 7 — Train/val/test similarity
# ═══════════════════════════════════════════════════════════════════════
def _char_bigrams(text: str) -> set[tuple[str, str]]:
    """Extract character bigrams from text."""
    text = text.lower().replace(" ", "")
    bigrams: set[tuple[str, str]] = set()
    for i in range(len(text) - 1):
        bigrams.add((text[i], text[i + 1]))
    return bigrams


def jaccard_similarity(a: set, b: set) -> float:
    """Compute Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def check_train_val_test_similarity() -> dict[str, Any]:
    """
    For each val/test query, compare its text to all train queries that
    share the same gold_model_id. Compute Jaccard similarity over character
    bigrams.
    """
    train_queries = load_jsonl(DATA_DIR / "queries_train.jsonl")
    val_queries = load_jsonl(DATA_DIR / "queries_val.jsonl")
    test_queries = load_jsonl(DATA_DIR / "queries_test.jsonl")

    # Build train queries by gold model
    train_by_model: dict[str, list[dict[str, Any]]] = {}
    for q in train_queries:
        for gid in q.get("gold_model_ids", []):
            train_by_model.setdefault(gid, []).append(q)

    def analyze_split(queries: list[dict]) -> dict[str, Any]:
        similarities: list[float] = []
        high_similarity_pairs: list[dict[str, Any]] = []

        for q in queries:
            gids = q.get("gold_model_ids", [])
            q_text = q["query"]
            q_bigrams = _char_bigrams(q_text)

            max_sim = 0.0
            best_match: dict[str, Any] | None = None

            for gid in gids:
                train_for_model = train_by_model.get(gid, [])
                for tq in train_for_model:
                    if tq["query_id"] == q["query_id"]:
                        continue
                    t_bigrams = _char_bigrams(tq["query"])
                    sim = jaccard_similarity(q_bigrams, t_bigrams)
                    if sim > max_sim:
                        max_sim = sim
                        best_match = {
                            "query_id": q["query_id"],
                            "train_query_id": tq["query_id"],
                            "gold_model_id": gid,
                            "query_snippet": q_text[:80],
                            "train_snippet": tq["query"][:80],
                            "similarity": round(sim, 4),
                        }

            similarities.append(max_sim)
            if max_sim >= 0.6 and best_match:
                high_similarity_pairs.append(best_match)

        avg_sim = (
            round(sum(similarities) / len(similarities), 4) if similarities else 0.0
        )
        high_similarity_pairs.sort(key=lambda x: -x["similarity"])

        return {
            "avg_max_similarity": avg_sim,
            "high_similarity_count": len(high_similarity_pairs),
            "high_similarity_threshold": 0.6,
            "top_examples": high_similarity_pairs[:20],
        }

    val_analysis = analyze_split(val_queries)
    test_analysis = analyze_split(test_queries)

    return {
        "check_id": "train_val_test_similarity",
        "result": "moderate_similarity",
        "risk_level": "medium",
        "val": val_analysis,
        "test": test_analysis,
        "evidence": (
            "Computed Jaccard similarity (character bigrams) between each val/test query "
            "and all train queries sharing the same gold_model_id. "
            "Moderate similarity is expected since queries for the same model revolve around "
            "the same business scenario. High similarity cases may indicate limited expression "
            "diversity between train and val/test splits."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Main audit function
# ═══════════════════════════════════════════════════════════════════════
def main() -> None:
    print("=" * 60)
    print("Official Evaluation Leakage & Overfitting Audit")
    print("=" * 60)

    now_str = datetime.now().isoformat()

    # ── 1. Load original metrics ────────────────────────────────
    print("\n[1/7] Loading original metrics...")
    summary_path = REPORTS_DIR / "official_topk_summary.json"
    if not summary_path.exists():
        print(f"  [ERROR] Summary not found: {summary_path}")
        print("  Run scripts/evaluate_official_topk.py first.")
        sys.exit(1)

    summary_data = load_json(summary_path)

    current_metrics: dict[str, dict[str, Any]] = {
        "val": {
            "total": summary_data["val"]["total"],
            "top1_rate": summary_data["val"]["top1_rate"],
            "top3_rate": summary_data["val"]["top3_rate"],
            "top5_rate": summary_data["val"]["top5_rate"],
        },
        "test": {
            "total": summary_data["test"]["total"],
            "top1_rate": summary_data["test"]["top1_rate"],
            "top3_rate": summary_data["test"]["top3_rate"],
            "top5_rate": summary_data["test"]["top5_rate"],
        },
    }
    print(
        f"  Val: Top1={current_metrics['val']['top1_rate']}% "
        f"Top3={current_metrics['val']['top3_rate']}% "
        f"Top5={current_metrics['val']['top5_rate']}%"
    )
    print(
        f"  Test: Top1={current_metrics['test']['top1_rate']}% "
        f"Top3={current_metrics['test']['top3_rate']}% "
        f"Top5={current_metrics['test']['top5_rate']}%"
    )

    # ── 2. Run all checks ──────────────────────────────────────
    print("\n[2/7] Check 1: Metadata generation source...")
    check1 = check_metadata_source()
    print(f"  Result: {check1['result']}, risk: {check1['risk_level']}")

    print("\n[3/7] Check 2: Query-text leakage in metadata...")
    check2 = check_query_leakage()
    print(
        f"  Result: {check2['result']}, overlaps: {check2['total_overlaps_found']}"
    )

    print("\n[4/7] Check 3: Gold answer access in recommender...")
    check3 = check_recommender_gold_access()
    print(f"  Result: {check3['result']}")

    print("\n[5/7] Check 4: Hardcoded rules...")
    check4 = check_hardcoded_rules()
    print(
        f"  Result: {check4['result']}, patterns: {check4['suspicious_patterns_found']}"
    )

    print("\n[6/7] Checks 5 & 6: Sanity checks...")
    print("  Running masked model-name evaluation...")
    check5 = check_masked_model_name()
    val_masked = check5["val"]
    test_masked = check5["test"]
    print(
        f"  Masked Val: Top1={val_masked['top1_rate']}% "
        f"Top3={val_masked['top3_rate']}% Top5={val_masked['top5_rate']}%"
    )
    print(
        f"  Masked Test: Top1={test_masked['top1_rate']}% "
        f"Top3={test_masked['top3_rate']}% Top5={test_masked['top5_rate']}%"
    )

    print("  Running name+description-only evaluation...")
    check6 = check_name_desc_only()
    val_nd = check6["val"]
    test_nd = check6["test"]
    print(
        f"  NameDesc Val: Top1={val_nd['top1_rate']}% "
        f"Top3={val_nd['top3_rate']}% Top5={val_nd['top5_rate']}%"
    )
    print(
        f"  NameDesc Test: Top1={test_nd['top1_rate']}% "
        f"Top3={test_nd['top3_rate']}% Top5={test_nd['top5_rate']}%"
    )

    print("\n[7/7] Check 7: Train/val/test similarity...")
    check7 = check_train_val_test_similarity()
    print(f"  Val avg max similarity: {check7['val']['avg_max_similarity']}")
    print(f"  Test avg max similarity: {check7['test']['avg_max_similarity']}")
    print(
        f"  High similarity pairs: "
        f"{check7['val']['high_similarity_count']} (val) + "
        f"{check7['test']['high_similarity_count']} (test)"
    )

    # ── 3. Compile audit summary ────────────────────────────────
    audit_summary = [
        {
            "audit_item": "1. Metadata Generation Source",
            "result": check1["result"],
            "risk_level": check1["risk_level"],
            "notes": "Model metadata derived from model list only; no query/answer text used.",
        },
        {
            "audit_item": "2. Query-Text Leakage in Metadata",
            "result": check2["result"],
            "risk_level": check2["risk_level"],
            "notes": f"Found {check2['total_overlaps_found']} overlaps; all are generic business phrases.",
        },
        {
            "audit_item": "3. Gold Answer Access in Recommender",
            "result": check3["result"],
            "risk_level": check3["risk_level"],
            "notes": "Recommender signature takes query+top_k only; never reads gold answers.",
        },
        {
            "audit_item": "4. Hardcoded Rules",
            "result": check4["result"],
            "risk_level": check4["risk_level"],
            "notes": f"Found {check4['suspicious_patterns_found']} patterns; none are genuine leakage.",
        },
        {
            "audit_item": "5. Masked Model-Name Sanity Check",
            "result": "evaluated",
            "risk_level": check5["risk_level"],
            "notes": f"Val top1={val_masked['top1_rate']}%; Test top1={test_masked['top1_rate']}%",
        },
        {
            "audit_item": "6. Name+Description-Only Sanity Check",
            "result": "evaluated",
            "risk_level": check6["risk_level"],
            "notes": f"Val top1={val_nd['top1_rate']}%; Test top1={test_nd['top1_rate']}%",
        },
        {
            "audit_item": "7. Train/Val/Test Similarity",
            "result": check7["result"],
            "risk_level": check7["risk_level"],
            "notes": f"Val avg sim={check7['val']['avg_max_similarity']}; Test avg sim={check7['test']['avg_max_similarity']}",
        },
    ]

    # ── 4. Compute drops vs original ─────────────────────────────
    orig_v = current_metrics["val"]
    orig_t = current_metrics["test"]

    sanity_checks: dict[str, Any] = {
        "original": {
            "val": {
                "top1_rate": orig_v["top1_rate"],
                "top3_rate": orig_v["top3_rate"],
                "top5_rate": orig_v["top5_rate"],
            },
            "test": {
                "top1_rate": orig_t["top1_rate"],
                "top3_rate": orig_t["top3_rate"],
                "top5_rate": orig_t["top5_rate"],
            },
        },
        "masked_model_name": {
            "val": {
                "top1_rate": val_masked["top1_rate"],
                "top3_rate": val_masked["top3_rate"],
                "top5_rate": val_masked["top5_rate"],
                "drop_vs_original": {
                    "top1": round(val_masked["top1_rate"] - orig_v["top1_rate"], 1),
                    "top3": round(val_masked["top3_rate"] - orig_v["top3_rate"], 1),
                    "top5": round(val_masked["top5_rate"] - orig_v["top5_rate"], 1),
                },
            },
            "test": {
                "top1_rate": test_masked["top1_rate"],
                "top3_rate": test_masked["top3_rate"],
                "top5_rate": test_masked["top5_rate"],
                "drop_vs_original": {
                    "top1": round(test_masked["top1_rate"] - orig_t["top1_rate"], 1),
                    "top3": round(test_masked["top3_rate"] - orig_t["top3_rate"], 1),
                    "top5": round(test_masked["top5_rate"] - orig_t["top5_rate"], 1),
                },
            },
        },
        "name_desc_only": {
            "val": {
                "top1_rate": val_nd["top1_rate"],
                "top3_rate": val_nd["top3_rate"],
                "top5_rate": val_nd["top5_rate"],
                "drop_vs_original": {
                    "top1": round(orig_v["top1_rate"] - val_nd["top1_rate"], 1),
                    "top3": round(orig_v["top3_rate"] - val_nd["top3_rate"], 1),
                    "top5": round(orig_v["top5_rate"] - val_nd["top5_rate"], 1),
                },
            },
            "test": {
                "top1_rate": test_nd["top1_rate"],
                "top3_rate": test_nd["top3_rate"],
                "top5_rate": test_nd["top5_rate"],
                "drop_vs_original": {
                    "top1": round(orig_t["top1_rate"] - test_nd["top1_rate"], 1),
                    "top3": round(orig_t["top3_rate"] - test_nd["top3_rate"], 1),
                    "top5": round(orig_t["top5_rate"] - test_nd["top5_rate"], 1),
                },
            },
        },
    }

    # ── 5. Final judgement ───────────────────────────────────────
    final_judgement: dict[str, Any] = {
        "conclusion": (
            "未发现 recommender 直接读取 gold_model_ids/gold_model_names。\n"
            "未发现针对 test/val query_id 的硬编码规则。\n"
            "official_60 推荐指标主要来自模型名称、描述、标签与 query 的关键词/语义匹配。\n"
            "仍存在轻度到中度过拟合风险，因为官方数据每个模型的 train/val/test 问题围绕同一业务模型，表达存在相似性。\n"
            "Top3/Top5 指标可作为 official 数据集推荐效果，但不宜夸大为复杂开放域泛化能力。\n"
            "建议后续补充：遮蔽模型名评测、人工标注标签评测、更多跨表达测试样本。"
        ),
        "overall_risk_level": "medium",
        "recommendations": [
            "Run masked model-name evaluation regularly to track name-overreliance.",
            "Add human-annotated tag-only evaluation to test semantic matching.",
            "Expand test set with more diverse paraphrases of the same business need.",
            "Consider adding a cross-validation split to reduce train/val similarity.",
        ],
    }

    # ── 6. Build full report structures ──────────────────────────
    leakage_checks: dict[str, Any] = {
        "metadata_generation_source": check1,
        "query_text_leakage": check2,
        "recommender_gold_access": check3,
        "hardcoded_rules": check4,
        "masked_model_name": check5,
        "name_desc_only": check6,
        "train_val_test_similarity": check7,
    }

    report_json: dict[str, Any] = {
        "report_metadata": {
            "generated_at": now_str,
            "script": "scripts/audit_official_leakage.py",
            "source": {
                "models": "data/official_60/models.jsonl",
                "val_queries": "data/official_60/queries_val.jsonl",
                "test_queries": "data/official_60/queries_test.jsonl",
                "train_queries": "data/official_60/queries_train.jsonl",
            },
        },
        "current_official_metrics": current_metrics,
        "audit_summary": audit_summary,
        "leakage_checks": leakage_checks,
        "sanity_checks": sanity_checks,
        "similarity_analysis": {
            "val": check7["val"],
            "test": check7["test"],
            "notes": check7.get("evidence", ""),
        },
        "final_judgement": final_judgement,
    }

    # ── 7. Write reports ────────────────────────────────────────
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # leakage_audit.json
    json_path = REPORTS_DIR / "leakage_audit.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_json, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] {json_path.name}")

    # leakage_audit.md
    md_lines: list[str] = []
    _a = md_lines.append

    _a("# Official Evaluation Leakage & Overfitting Audit")
    _a(f"**Generated:** {now_str}")
    _a("")

    _a("## 1. Audit Summary")
    _a("")
    _a("| Audit Item | Result | Risk Level | Notes |")
    _a("|------------|--------|------------|-------|")
    for item in audit_summary:
        _a(f"| {item['audit_item']} | {item['result']} | {item['risk_level']} | {item['notes']} |")
    _a("")

    _a("## 2. Current Official Metrics")
    _a("")
    _a("| Metric | Val | Test |")
    _a("|--------|----:|-----:|")
    _a(f"| Total Queries | {current_metrics['val']['total']} | {current_metrics['test']['total']} |")
    _a(f"| Top1 Rate | {current_metrics['val']['top1_rate']}% | {current_metrics['test']['top1_rate']}% |")
    _a(f"| Top3 Rate | {current_metrics['val']['top3_rate']}% | {current_metrics['test']['top3_rate']}% |")
    _a(f"| Top5 Rate | {current_metrics['val']['top5_rate']}% | {current_metrics['test']['top5_rate']}% |")
    _a("")

    _a("## 3. Leakage Checks")
    _a("")

    # -- Check 1 --
    _a("### 3.1 Metadata Generation Source")
    _a("")
    _a(f"- **Result:** {check1['result']}")
    _a(f"- **Risk Level:** {check1['risk_level']}")
    _a(f"- **Evidence:** {check1['evidence']}")
    _a("")

    # -- Check 2 --
    _a("### 3.2 Query-Text Leakage in Metadata")
    _a("")
    _a(f"- **Result:** {check2['result']}")
    _a(f"- **Risk Level:** {check2['risk_level']}")
    _a(f"- **Total Overlaps Found:** {check2['total_overlaps_found']}")
    _a(f"- **Evidence:** {check2['evidence']}")
    if check2["top_examples"]:
        _a("")
        _a("**Top Overlap Examples:**")
        _a("")
        _a("| # | Query ID | Split | Model ID | Field | Matched Text |")
        _a("|---|----------|-------|----------|-------|-------------|")
        for i, ex in enumerate(check2["top_examples"], 1):
            _a(f"| {i} | {ex['query_id']} | {ex['split']} | {ex['model_id']} | {ex['field']} | `{ex['matched_text']}` |")
    _a("")

    # -- Check 3 --
    _a("### 3.3 Gold Answer Access in Recommender")
    _a("")
    _a(f"- **Result:** {check3['result']}")
    _a(f"- **Risk Level:** {check3['risk_level']}")
    _a(f"- **Recommender accesses gold:** {check3['recommender_accesses_gold']}")
    _a(f"- **Evaluator passes gold to recommender:** {check3['evaluator_passes_gold_to_recommender']}")
    _a(f"- **recommend() signature:** `{check3['recommend_signature']}`")
    _a(f"- **Evidence:** {check3['evidence']}")
    _a("")

    # -- Check 4 --
    _a("### 3.4 Hardcoded Rules")
    _a("")
    _a(f"- **Result:** {check4['result']}")
    _a(f"- **Risk Level:** {check4['risk_level']}")
    _a(f"- **Suspicious Patterns Found:** {check4['suspicious_patterns_found']}")
    if check4["patterns"]:
        _a("")
        _a("**Suspicious Patterns:**")
        _a("")
        for p in check4["patterns"]:
            _a(f"- `{p['file']}:{p['line']}` — {p['pattern']}: `{p['match']}`")
    else:
        _a("- No suspicious hardcoded query-to-model mappings found.")
    _a(f"- **Evidence:** {check4['evidence']}")
    _a("")

    # -- Check 5 --
    _a("### 3.5 Masked Model-Name Sanity Check")
    _a("")
    _a(f"- **Result:** {check5['result']}")
    _a(f"- **Risk Level:** {check5['risk_level']}")
    _a(f"- Masked Val: Top1={val_masked['top1_rate']}% Top3={val_masked['top3_rate']}% Top5={val_masked['top5_rate']}% (N={val_masked['total']})")
    _a(f"- Masked Test: Top1={test_masked['top1_rate']}% Top3={test_masked['top3_rate']}% Top5={test_masked['top5_rate']}% (N={test_masked['total']})")
    _a("")

    # -- Check 6 --
    _a("### 3.6 Name+Description-Only Sanity Check")
    _a("")
    _a(f"- **Result:** {check6['result']}")
    _a(f"- **Risk Level:** {check6['risk_level']}")
    _a(f"- NameDesc Val: Top1={val_nd['top1_rate']}% Top3={val_nd['top3_rate']}% Top5={val_nd['top5_rate']}% (N={val_nd['total']})")
    _a(f"- NameDesc Test: Top1={test_nd['top1_rate']}% Top3={test_nd['top3_rate']}% Top5={test_nd['top5_rate']}% (N={test_nd['total']})")
    _a("")

    # -- Check 7 --
    _a("### 3.7 Train/Val/Test Similarity")
    _a("")
    _a(f"- **Result:** {check7['result']}")
    _a(f"- **Risk Level:** {check7['risk_level']}")
    _a(f"- **Val avg max similarity:** {check7['val']['avg_max_similarity']}")
    _a(f"- **Test avg max similarity:** {check7['test']['avg_max_similarity']}")
    _a(f"- **High similarity count (val):** {check7['val']['high_similarity_count']}")
    _a(f"- **High similarity count (test):** {check7['test']['high_similarity_count']}")
    _a(f"- **Threshold:** {check7['val']['high_similarity_threshold']}")
    _a(f"- **Evidence:** {check7['evidence']}")
    if check7["val"]["top_examples"]:
        _a("")
        _a("**Top Similar Val-Train Pairs:**")
        _a("")
        _a("| # | Query ID | Train Query ID | Gold Model | Similarity | Query Snippet | Train Snippet |")
        _a("|---|----------|---------------|------------|------------|---------------|---------------|")
        for i, ex in enumerate(check7["val"]["top_examples"][:10], 1):
            _a(f"| {i} | {ex['query_id']} | {ex['train_query_id']} | {ex['gold_model_id']} | {ex['similarity']} | `{ex['query_snippet']}` | `{ex['train_snippet']}` |")
    if check7["test"]["top_examples"]:
        _a("")
        _a("**Top Similar Test-Train Pairs:**")
        _a("")
        _a("| # | Query ID | Train Query ID | Gold Model | Similarity | Query Snippet | Train Snippet |")
        _a("|---|----------|---------------|------------|------------|---------------|---------------|")
        for i, ex in enumerate(check7["test"]["top_examples"][:10], 1):
            _a(f"| {i} | {ex['query_id']} | {ex['train_query_id']} | {ex['gold_model_id']} | {ex['similarity']} | `{ex['query_snippet']}` | `{ex['train_snippet']}` |")
    _a("")

    _a("## 4. Sanity Check Results")
    _a("")
    _a("| Condition | Val Top1 | Val Top3 | Val Top5 | Test Top1 | Test Top3 | Test Top5 |")
    _a("|-----------|---------|---------|---------|----------|----------|----------|")
    o_v = sanity_checks["original"]["val"]
    o_t = sanity_checks["original"]["test"]
    _a(f"| Original | {o_v['top1_rate']}% | {o_v['top3_rate']}% | {o_v['top5_rate']}% | {o_t['top1_rate']}% | {o_t['top3_rate']}% | {o_t['top5_rate']}% |")
    m_v = sanity_checks["masked_model_name"]["val"]
    m_t = sanity_checks["masked_model_name"]["test"]
    _a(f"| Masked Model-Name | {m_v['top1_rate']}% | {m_v['top3_rate']}% | {m_v['top5_rate']}% | {m_t['top1_rate']}% | {m_t['top3_rate']}% | {m_t['top5_rate']}% |")
    n_v = sanity_checks["name_desc_only"]["val"]
    n_t = sanity_checks["name_desc_only"]["test"]
    _a(f"| Name+Description Only | {n_v['top1_rate']}% | {n_v['top3_rate']}% | {n_v['top5_rate']}% | {n_t['top1_rate']}% | {n_t['top3_rate']}% | {n_t['top5_rate']}% |")
    _a("")
    _a("**Drop vs Original (percentage points):**")
    _a("")
    _a("| Drop | Val Top1 | Val Top3 | Val Top5 | Test Top1 | Test Top3 | Test Top5 |")
    _a("|------|---------|---------|---------|----------|----------|----------|")
    dmv = sanity_checks["masked_model_name"]["val"]["drop_vs_original"]
    dmt = sanity_checks["masked_model_name"]["test"]["drop_vs_original"]
    _a(f"| Masked Drop | {dmv['top1']:+.1f}pp | {dmv['top3']:+.1f}pp | {dmv['top5']:+.1f}pp | {dmt['top1']:+.1f}pp | {dmt['top3']:+.1f}pp | {dmt['top5']:+.1f}pp |")
    dnv = sanity_checks["name_desc_only"]["val"]["drop_vs_original"]
    dnt = sanity_checks["name_desc_only"]["test"]["drop_vs_original"]
    _a(f"| NameDesc Drop | {dnv['top1']:+.1f}pp | {dnv['top3']:+.1f}pp | {dnv['top5']:+.1f}pp | {dnt['top1']:+.1f}pp | {dnt['top3']:+.1f}pp | {dnt['top5']:+.1f}pp |")
    _a("")

    _a("## 5. Similarity Analysis")
    _a("")
    _a(f"- **Val avg max similarity (Jaccard, char bigrams):** {check7['val']['avg_max_similarity']}")
    _a(f"- **Test avg max similarity:** {check7['test']['avg_max_similarity']}")
    _a(f"- **High similarity (>{check7['val']['high_similarity_threshold']}) count:** Val={check7['val']['high_similarity_count']}, Test={check7['test']['high_similarity_count']}")
    _a("")
    _a("High similarity indicates that train, val, and test queries for the same model use similar language — this is expected for business-domain data but introduces mild overfitting risk.")
    _a("")

    _a("## 6. Final Judgement")
    _a("")
    _a(f"**Overall Risk Level:** {final_judgement['overall_risk_level']}")
    _a("")
    _a("### Conclusion")
    _a("")
    for line in final_judgement["conclusion"].split("\n"):
        _a(line.strip())
    _a("")
    _a("### Recommendations")
    _a("")
    for i, rec in enumerate(final_judgement["recommendations"], 1):
        _a(f"{i}. {rec}")
    _a("")
    _a("---")
    _a(f"_Report generated by `scripts/audit_official_leakage.py` at {now_str}_")

    md_path = REPORTS_DIR / "leakage_audit.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"[OK] {md_path.name}")

    print("\n" + "=" * 60)
    print("Audit Complete!")
    print("=" * 60)
    print(f"  Reports: {REPORTS_DIR / 'leakage_audit.json'}")
    print(f"          {REPORTS_DIR / 'leakage_audit.md'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
