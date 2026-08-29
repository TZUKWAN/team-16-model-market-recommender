#!/usr/bin/env python3
"""Generate synthetic development data from the official 60-model dataset.

The generated records are for downstream development and robustness testing.
They are explicitly marked as synthetic and must not be treated as official
competition samples or real bank production data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = BASE_DIR / "data" / "official"
SYNTHETIC_DIR = BASE_DIR / "data" / "synthetic"
EVAL_SYNTHETIC_DIR = BASE_DIR / "data" / "eval_synthetic"

SOURCE = "synthetic_official_expansion"
ANNOTATION_VERSION = "synthetic_v1_rule_templates"

DOMAIN_LABEL = {
    "credit_risk": "信贷风控",
    "customer_marketing": "客户营销",
    "operation_management": "运营管理",
}

DOMAIN_ACTORS = {
    "credit_risk": ["风控团队", "授信审批岗", "贷前审查人员", "风险经理", "客户经理"],
    "customer_marketing": ["零售团队", "客户经理", "营销人员", "财富顾问", "支行经营团队"],
    "operation_management": ["运营管理团队", "网点负责人", "业务管理岗", "数据运营人员", "合规运营人员"],
}

DOMAIN_GOALS = {
    "credit_risk": ["降低风险", "提升审批质量", "提前识别异常", "控制不良率", "辅助授信决策"],
    "customer_marketing": ["提升转化率", "筛选高意向客户", "提高触达效率", "减少客户流失", "提升客户价值"],
    "operation_management": ["提升运营效率", "提前预警问题", "优化资源配置", "识别异常行为", "辅助经营决策"],
}

QUESTION_ENDINGS = [
    "应该选哪个模型？",
    "推荐用什么模型？",
    "哪个模型最适合？",
    "有什么合适的模型可以用？",
    "模型市场里该找哪个模型？",
    "请给一个可落地的模型推荐。",
]

NOISE_PREFIXES = [
    "月底要做专题汇报，",
    "客户经理反馈比较着急，",
    "我们想先做一版试点，",
    "不想让科技同事反复人工筛选，",
    "希望用现有模型资产快速支撑，",
]

NOISE_SUFFIXES = [
    "最好能说明适用边界。",
    "如果能输出名单就更好。",
    "需要考虑一线人员能不能直接用。",
    "希望结果方便后续跟进。",
    "也要注意合规和数据可用性。",
]

STYLE_PREFIXES = [
    "",
    "请问，",
    "业务上，",
    "从模型市场选型角度，",
    "站在农商行业务场景看，",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("，", ",").replace("？", "?").replace("。", ".")
    return text.lower()


def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def extract_field(description: str, keys: list[str]) -> str:
    for key in keys:
        pattern = rf"{key}\s*[:：]\s*(.+?)(?:\n|$)"
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1).strip(" 。；;")
    return ""


def compact_phrase(text: str, max_len: int = 42) -> str:
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[。；;]+$", "", text)
    if len(text) <= max_len:
        return text
    cut_chars = "，,；;。."
    for i in range(min(max_len, len(text) - 1), 12, -1):
        if text[i] in cut_chars:
            return text[:i]
    return text[:max_len]


def derive_model_profile(model: dict[str, Any], questions: list[dict[str, Any]]) -> dict[str, Any]:
    desc = model.get("description", "")
    name = model.get("canonical_name", "")
    domain = model.get("domain", "customer_marketing")
    target = extract_field(desc, ["目标用户", "目标客户", "适用对象"])
    positive = extract_field(desc, ["正样本"])
    purpose = extract_field(desc, ["用途", "业务用途"])

    tag_counter: Counter[str] = Counter()
    task_counter: Counter[str] = Counter()
    for q in questions:
        tag_counter.update(q.get("expected_tags", []))
        task = q.get("intent_task", "")
        if task:
            task_counter[task] += 1

    tags = [tag for tag, _ in tag_counter.most_common()]
    if DOMAIN_LABEL.get(domain) and DOMAIN_LABEL[domain] not in tags:
        tags.insert(0, DOMAIN_LABEL[domain])

    seed_queries = [q.get("user_query", "") for q in questions if q.get("user_query")]

    return {
        "model_id": model.get("model_id", ""),
        "model_name": name,
        "domain": domain,
        "target": compact_phrase(target) if target else "",
        "positive": compact_phrase(positive) if positive else "",
        "purpose": compact_phrase(purpose) if purpose else "",
        "tags": tags[:6],
        "intent_task": task_counter.most_common(1)[0][0] if task_counter else "model_recommendation",
        "seed_queries": seed_queries,
    }


def model_keywords(name: str) -> list[str]:
    cleaned = re.sub(r"模型|评分卡|预测|推荐|分析|识别|预警|挖掘|：|:", " ", name)
    parts = [p.strip() for p in re.split(r"[\s_/、\-]+", cleaned) if len(p.strip()) >= 2]
    if not parts:
        return [name]
    return parts[:4]


def build_templates(profile: dict[str, Any]) -> list[tuple[str, str]]:
    name = profile["model_name"]
    domain = profile["domain"]
    domain_label = DOMAIN_LABEL.get(domain, "银行业务")
    tags = "、".join(profile["tags"][:3]) or domain_label
    target = profile["target"] or f"{domain_label}相关客户"
    purpose = profile["purpose"] or f"完成{tags}场景下的模型选型"
    positive = profile["positive"] or "未来一段时间内发生目标业务行为的客户"
    keywords = model_keywords(name)
    keyword_s = "、".join(keywords[:3])
    actors = DOMAIN_ACTORS.get(domain, ["业务人员"])
    goals = DOMAIN_GOALS.get(domain, ["提升业务效果"])

    templates: list[tuple[str, str]] = [
        ("direct_name", f"{name}适合解决什么业务需求？"),
        ("direct_select", f"业务人员想找{name}这一类能力，{random.choice(QUESTION_ENDINGS)}"),
        ("target_goal", f"针对{target}，希望{random.choice(goals)}，{random.choice(QUESTION_ENDINGS)}"),
        ("purpose_select", f"{purpose}，模型市场里应该优先看哪个模型？"),
        ("positive_sample", f"如果正样本定义是{positive}，需要做{tags}，{random.choice(QUESTION_ENDINGS)}"),
        ("actor_need", f"{random.choice(actors)}需要在{domain_label}场景中处理{keyword_s}问题，{random.choice(QUESTION_ENDINGS)}"),
        ("business_plain", f"我们行想围绕{keyword_s}做模型选型，目标是{random.choice(goals)}，{random.choice(QUESTION_ENDINGS)}"),
        ("result_oriented", f"希望输出可跟进的名单、评分或预测结果，用于{purpose}，推荐哪个模型？"),
        ("boundary", f"在{domain_label}场景下，既要{random.choice(goals)}又要控制适用边界，哪个模型更合适？"),
        ("short_question", f"{keyword_s}场景用什么模型？"),
    ]

    for seed in profile["seed_queries"][:4]:
        templates.append(("seed_rewrite", rewrite_seed_question(seed)))

    return templates


def rewrite_seed_question(seed: str) -> str:
    seed = seed.strip()
    replacements = [
        ("用什么模型", "推荐哪个模型"),
        ("哪个模型", "什么模型"),
        ("有什么合适的模型", "模型市场里该选哪个"),
        ("如何", "怎么"),
        ("需要", "想要"),
        ("推荐哪个", "应该选哪个"),
    ]
    for old, new in replacements:
        if old in seed:
            seed = seed.replace(old, new, 1)
            break
    if not seed.endswith(("？", "?", "。")):
        seed += "？"
    return seed


def decorate_query(base: str, difficulty: str) -> str:
    prefix = random.choice(STYLE_PREFIXES)
    query = prefix + base
    if difficulty in {"medium", "hard", "noisy"} and random.random() < 0.45:
        query = random.choice(NOISE_PREFIXES) + query
    if difficulty in {"hard", "noisy"} and random.random() < 0.65:
        query = query.rstrip("？?。") + "，" + random.choice(NOISE_SUFFIXES)
    if difficulty == "noisy" and random.random() < 0.3:
        query = query.replace("模型", "模形", 1) if "模型" in query else query + " 先看看有没有现成能力。"
    return query


def build_record(idx: int, profile: dict[str, Any], template_id: str, query: str, split: str, difficulty: str) -> dict[str, Any]:
    return {
        "synthetic_id": f"syn_{idx:06d}",
        "user_query": query,
        "gold_model_id": profile["model_id"],
        "gold_model_name": profile["model_name"],
        "split": split,
        "intent_primary": "model_recommendation",
        "intent_domain": profile["domain"],
        "intent_task": profile["intent_task"],
        "expected_tags": profile["tags"],
        "difficulty": difficulty,
        "source": SOURCE,
        "annotation_version": ANNOTATION_VERSION,
        "generation_template_id": template_id,
        "synthetic": True,
        "query_hash": stable_hash(normalize_text(query)),
        "needs_review": False,
    }


def split_for_index(idx: int) -> str:
    mod = idx % 20
    if mod < 14:
        return "train"
    if mod < 17:
        return "val"
    return "test"


def generate_records(total: int, seed: int) -> list[dict[str, Any]]:
    random.seed(seed)
    models = load_jsonl(OFFICIAL_DIR / "model_catalog_structured.jsonl")
    questions = load_jsonl(OFFICIAL_DIR / "questions_all.jsonl")
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for q in questions:
        by_model[q.get("gold_model_id", "")].append(q)

    profiles = [derive_model_profile(m, by_model.get(m.get("model_id", ""), [])) for m in models]
    profiles = [p for p in profiles if p["model_id"] and p["model_name"]]
    if not profiles:
        raise RuntimeError("No official model profiles found.")

    target_per_model = total // len(profiles)
    remainder = total % len(profiles)
    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    next_idx = 1

    for model_idx, profile in enumerate(profiles):
        need = target_per_model + (1 if model_idx < remainder else 0)
        templates = build_templates(profile)
        generated_for_model = 0
        attempt = 0
        while generated_for_model < need and attempt < need * 20:
            attempt += 1
            template_id, base = random.choice(templates)
            difficulty = random.choices(
                ["easy", "medium", "hard", "noisy"],
                weights=[0.22, 0.43, 0.25, 0.10],
                k=1,
            )[0]
            query = decorate_query(base, difficulty)
            q_hash = stable_hash(normalize_text(query))
            if q_hash in seen_hashes:
                continue
            seen_hashes.add(q_hash)
            split = split_for_index(next_idx)
            records.append(build_record(next_idx, profile, template_id, query, split, difficulty))
            next_idx += 1
            generated_for_model += 1

    random.shuffle(records)
    for idx, row in enumerate(records, start=1):
        row["synthetic_id"] = f"syn_{idx:06d}"
    return records


def write_eval_files(records: list[dict[str, Any]]) -> None:
    intent_records = [
        {
            "test_id": r["synthetic_id"],
            "query": r["user_query"],
            "expected_domain": r["intent_domain"],
            "source": SOURCE,
            "difficulty": r["difficulty"],
        }
        for r in records
    ]
    tag_records = [
        {
            "test_id": r["synthetic_id"],
            "query": r["user_query"],
            "expected_tags": r["expected_tags"],
            "difficulty": r["difficulty"],
            "source": SOURCE,
        }
        for r in records
    ]
    topk_records = [
        {
            "test_id": r["synthetic_id"],
            "query": r["user_query"],
            "gold_model_id": r["gold_model_id"],
            "gold_model_name": r["gold_model_name"],
            "expected_model_ids": [r["gold_model_id"]],
            "k": 5,
            "scenario": r["intent_domain"],
            "difficulty": r["difficulty"],
            "source": SOURCE,
        }
        for r in records
    ]
    write_jsonl(EVAL_SYNTHETIC_DIR / "intent_eval_synthetic.jsonl", intent_records)
    write_jsonl(EVAL_SYNTHETIC_DIR / "tag_eval_synthetic.jsonl", tag_records)
    write_jsonl(EVAL_SYNTHETIC_DIR / "topk_eval_synthetic.jsonl", topk_records)


def write_outputs(records: list[dict[str, Any]], total: int, seed: int) -> None:
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)

    write_jsonl(SYNTHETIC_DIR / "synthetic_questions_all.jsonl", records)
    for split in ["train", "val", "test"]:
        split_records = [r for r in records if r["split"] == split]
        write_jsonl(SYNTHETIC_DIR / f"synthetic_questions_{split}.jsonl", split_records)

    write_eval_files(records)

    split_counts = Counter(r["split"] for r in records)
    domain_counts = Counter(r["intent_domain"] for r in records)
    difficulty_counts = Counter(r["difficulty"] for r in records)
    model_counts = Counter(r["gold_model_id"] for r in records)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE,
        "annotation_version": ANNOTATION_VERSION,
        "seed": seed,
        "requested_total": total,
        "actual_total": len(records),
        "official_model_count": len(model_counts),
        "split_counts": dict(sorted(split_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "min_records_per_model": min(model_counts.values()) if model_counts else 0,
        "max_records_per_model": max(model_counts.values()) if model_counts else 0,
        "files": {
            "all": "data/synthetic/synthetic_questions_all.jsonl",
            "train": "data/synthetic/synthetic_questions_train.jsonl",
            "val": "data/synthetic/synthetic_questions_val.jsonl",
            "test": "data/synthetic/synthetic_questions_test.jsonl",
            "intent_eval": "data/eval_synthetic/intent_eval_synthetic.jsonl",
            "tag_eval": "data/eval_synthetic/tag_eval_synthetic.jsonl",
            "topk_eval": "data/eval_synthetic/topk_eval_synthetic.jsonl",
        },
        "limitations": [
            "Synthetic records are generated by deterministic templates and official model metadata.",
            "They are suitable for development, UI testing, robustness checks, and bootstrapping.",
            "They must not be reported as official competition samples or real bank production data.",
            "They do not prove hidden-set performance or real LLM capability.",
        ],
    }
    (SYNTHETIC_DIR / "synthetic_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def validate_records(records: list[dict[str, Any]], total: int) -> None:
    if len(records) != total:
        raise RuntimeError(f"Expected {total} records, got {len(records)}")
    hashes = [r["query_hash"] for r in records]
    if len(hashes) != len(set(hashes)):
        raise RuntimeError("Duplicate normalized queries found.")
    missing = [
        r["synthetic_id"]
        for r in records
        if not r.get("gold_model_id") or not r.get("gold_model_name") or not r.get("expected_tags")
    ]
    if missing:
        raise RuntimeError(f"Records missing labels: {missing[:10]}")
    model_count = len({r["gold_model_id"] for r in records})
    if model_count < 60:
        raise RuntimeError(f"Expected coverage of 60 official models, got {model_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic development data from official model/question data.")
    parser.add_argument("--total", type=int, default=3000, help="Total synthetic records to generate.")
    parser.add_argument("--seed", type=int, default=20260706, help="Random seed for reproducible generation.")
    args = parser.parse_args()

    if args.total < 600:
        raise SystemExit("--total should be at least 600 to cover all official models with useful variety.")

    records = generate_records(args.total, args.seed)
    validate_records(records, args.total)
    write_outputs(records, args.total, args.seed)

    print(f"Generated {len(records)} synthetic records.")
    print(f"Output: {SYNTHETIC_DIR / 'synthetic_questions_all.jsonl'}")
    print(f"Manifest: {SYNTHETIC_DIR / 'synthetic_manifest.json'}")
    print(f"Synthetic eval dir: {EVAL_SYNTHETIC_DIR}")


if __name__ == "__main__":
    main()
