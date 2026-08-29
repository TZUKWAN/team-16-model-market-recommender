#!/usr/bin/env python3
"""Generate deterministic robustness evaluation data from official questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
OFFICIAL_PATH = BASE_DIR / "data" / "official" / "questions_all.jsonl"
OUT_DIR = BASE_DIR / "data" / "eval_robustness"
OUT_PATH = OUT_DIR / "robust_eval.jsonl"


SYNONYM_REPLACEMENTS = [
    ("如何", "怎么"),
    ("客户", "客群"),
    ("识别", "判断"),
    ("模型", "算法模型"),
    ("推荐", "匹配推荐"),
]

TYPO_REPLACEMENTS = [
    ("客户", "客戶"),
    ("风险", "风險"),
    ("模型", "模形"),
    ("贷款", "贷 款"),
    ("营销", "营 销"),
]


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


def synonym_rewrite(query: str) -> str:
    rewritten = query
    for old, new in SYNONYM_REPLACEMENTS:
        rewritten = rewritten.replace(old, new)
    return rewritten if rewritten != query else f"请帮我换个说法理解：{query}"


def colloquial_rewrite(query: str) -> str:
    return f"我们业务上想问一下，{query} 麻烦直接给个模型推荐。"


def typo_noise_rewrite(query: str) -> str:
    rewritten = query
    for old, new in TYPO_REPLACEMENTS:
        rewritten = rewritten.replace(old, new)
    if rewritten == query:
        rewritten = query.replace("，", " ， ").replace("？", " ? ")
    return rewritten


def long_context_rewrite(query: str) -> str:
    return (
        f"{query} 请同时说明适用场景、需要哪些输入数据、输出结果是什么，"
        "以及上线前需要注意的数据授权和合规边界。"
    )


def mixed_context_rewrite(query: str, domain: str) -> str:
    distractor = {
        "credit_risk": "另外我们也关心营销触达成本，但本次优先解决风险判断。",
        "customer_marketing": "另外也希望兼顾风险合规要求，但本次优先解决营销转化。",
        "operation_management": "另外也关注客户体验，但本次优先解决运营监测和流程优化。",
    }.get(domain, "另外有一些其他业务关注点，但请优先围绕原问题推荐。")
    return f"{query} {distractor}"


def build_variants(record: dict[str, Any]) -> list[dict[str, Any]]:
    query = str(record.get("user_query") or record.get("query") or "").strip()
    domain = str(record.get("intent_domain") or record.get("expected_domain") or "").strip()
    gold_model_id = str(record.get("gold_model_id") or "").strip()
    gold_model_name = str(record.get("gold_model_name") or "").strip()
    expected_tags = record.get("expected_tags") or []
    source_id = str(record.get("question_id") or record.get("test_id") or "").strip()
    split = str(record.get("split") or "official").strip()

    transforms = [
        ("synonym", synonym_rewrite),
        ("colloquial", colloquial_rewrite),
        ("typo_noise", typo_noise_rewrite),
        ("long_context", long_context_rewrite),
        ("mixed_context", lambda q: mixed_context_rewrite(q, domain)),
    ]
    variants: list[dict[str, Any]] = []
    for perturbation_type, transform in transforms:
        variants.append({
            "robust_id": f"{source_id}_{perturbation_type}",
            "source_question_id": source_id,
            "split": split,
            "perturbation_type": perturbation_type,
            "query": transform(query),
            "original_query": query,
            "expected_domain": domain,
            "expected_tags": expected_tags,
            "gold_model_id": gold_model_id,
            "gold_model_name": gold_model_name,
            "source": "robust_official_perturbation",
        })
    return variants


def generate(limit: int | None = None) -> list[dict[str, Any]]:
    source = load_jsonl(OFFICIAL_PATH)
    if limit is not None:
        source = source[:limit]
    records: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for record in source:
        for variant in build_variants(record):
            key = variant["query"]
            if key in seen_queries:
                continue
            seen_queries.add(key)
            records.append(variant)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Optional source question limit for tests.")
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    records = generate(limit=args.limit)
    write_jsonl(args.output, records)
    types = sorted({record["perturbation_type"] for record in records})
    print(f"Generated {len(records)} robust samples -> {args.output}")
    print(f"Perturbation types: {', '.join(types)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
