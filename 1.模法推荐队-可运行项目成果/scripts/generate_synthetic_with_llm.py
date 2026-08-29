#!/usr/bin/env python3
"""Generate LLM-enhanced synthetic development questions from official models.

This script never reads API keys from arguments and never prints secrets. Live
LLM generation is enabled only when the normal LLM environment is configured.
Dry-run mode is intentionally labeled as template data and must not be reported
as LLM-generated data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
OFFICIAL_DIR = BASE_DIR / "data" / "official"
DEFAULT_OUTPUT_DIR = BASE_DIR / "data" / "synthetic_llm"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from generate_synthetic_official_data import derive_model_profile, load_jsonl  # noqa: E402
from app.services.data_loader import build_synonym_map, load_tags  # noqa: E402
from app.services.demand_parser import DemandParser  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402


LIVE_SOURCE = "synthetic_llm_official_expansion"
DRY_RUN_SOURCE = "synthetic_llm_template_dry_run"
ANNOTATION_VERSION = "synthetic_v2_llm_assisted"
_TAG_SYNONYM_MAP: dict[str, str] | None = None

SYSTEM_PROMPT = """你是银行模型市场的数据合成助手。
只根据给定的官方模型元数据生成用户需求问句，不得创造新模型、不得改变目标模型、不得包含真实客户姓名、证件号、手机号、银行卡号或机构敏感信息。
输出必须是 JSON：{"queries": ["问题1", "问题2"]}。
每个问题要像业务人员自然提问，表达可以包含口语化、目标、约束、数据条件或输出要求，但不能直接暴露这是合成数据。
"""


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = text.replace("，", ",").replace("？", "?").replace("。", ".")
    return text.lower()


def stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_profiles(limit_models: int | None = None) -> list[dict[str, Any]]:
    models = load_jsonl(OFFICIAL_DIR / "model_catalog_structured.jsonl")
    questions = load_jsonl(OFFICIAL_DIR / "questions_all.jsonl")
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        by_model[question.get("gold_model_id", "")].append(question)

    profiles = [derive_model_profile(model, by_model.get(model.get("model_id", ""), [])) for model in models]
    profiles = [profile for profile in profiles if profile.get("model_id") and profile.get("model_name")]
    if limit_models:
        profiles = profiles[:limit_models]
    return profiles


def build_user_prompt(profile: dict[str, Any], requested_count: int) -> str:
    payload = {
        "model_id": profile["model_id"],
        "model_name": profile["model_name"],
        "domain": profile["domain"],
        "target_customer_or_object": profile.get("target", ""),
        "positive_sample_definition": profile.get("positive", ""),
        "business_purpose": profile.get("purpose", ""),
        "expected_tags": profile.get("tags", [])[:8],
        "seed_queries": profile.get("seed_queries", [])[:4],
        "requested_query_count": requested_count,
    }
    return (
        "请为下面这个官方模型生成不同表达方式的银行业务需求问句。"
        "每条问句都必须仍然指向该模型，不要输出解释。\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def extract_queries(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    raw_queries = payload.get("queries") or payload.get("questions") or payload.get("items") or []
    queries: list[str] = []
    if not isinstance(raw_queries, list):
        return queries
    for item in raw_queries:
        if isinstance(item, str):
            query = item
        elif isinstance(item, dict):
            query = str(item.get("query") or item.get("user_query") or item.get("question") or "")
        else:
            query = ""
        query = re.sub(r"\s+", " ", query).strip()
        if 8 <= len(query) <= 180:
            queries.append(query)
    return queries


def dry_run_queries(profile: dict[str, Any], count: int) -> list[str]:
    name = profile["model_name"]
    target = profile.get("target") or "目标客群"
    purpose = profile.get("purpose") or "业务模型选型"
    tags = "、".join(profile.get("tags", [])[:3]) or "银行业务"
    patterns = [
        f"我们想针对{target}做{purpose}，模型市场里哪个模型比较适合？",
        f"客户经理需要一批和{tags}相关的名单或评分，能不能推荐合适模型？",
        f"如果业务目标是{purpose}，是否应该优先考虑{name}这类能力？",
        f"现在要围绕{target}提升经营效果，请帮我选一个可落地的模型。",
        f"请从现有模型资产里找一个能支撑{tags}场景的模型，并说明适用边界。",
    ]
    queries: list[str] = []
    while len(queries) < count:
        base = patterns[len(queries) % len(patterns)]
        suffix = "" if len(queries) < len(patterns) else f" 场景批次{len(queries) + 1}"
        queries.append(base + suffix)
    return queries


def normalize_tags(tags: list[str], synonym_map: dict[str, str]) -> set[str]:
    normalized: set[str] = set()
    for tag in tags:
        tag_text = str(tag).strip()
        if not tag_text:
            continue
        normalized.add(synonym_map.get(tag_text, tag_text))
    return normalized


def get_tag_synonym_map() -> dict[str, str]:
    global _TAG_SYNONYM_MAP
    if _TAG_SYNONYM_MAP is None:
        _TAG_SYNONYM_MAP = build_synonym_map(load_tags())
    return _TAG_SYNONYM_MAP


def validate_query(query: str, profile: dict[str, Any], parser: DemandParser) -> dict[str, Any]:
    parsed = parser.parse(query)
    synonym_map = get_tag_synonym_map()
    expected_tags = normalize_tags(profile.get("tags") or [], synonym_map)
    parsed_tags = normalize_tags(parsed.tags or [], synonym_map)
    tag_overlap = sorted(expected_tags & parsed_tags)
    domain_match = parsed.intent == profile["domain"]
    model_id_valid = bool(profile.get("model_id", "").startswith("OFFICIAL_"))
    pii_like = bool(re.search(r"1[3-9]\d{9}|\d{15,18}|\d{12,}", query))
    validation_passed = domain_match and bool(tag_overlap) and model_id_valid and not pii_like
    return {
        "parser_intent": parsed.intent,
        "domain_match": domain_match,
        "tag_overlap": tag_overlap,
        "tag_overlap_count": len(tag_overlap),
        "model_id_valid": model_id_valid,
        "pii_like": pii_like,
        "validation_passed": validation_passed,
    }


def split_for_index(index: int) -> str:
    mod = index % 20
    if mod < 14:
        return "train"
    if mod < 17:
        return "val"
    return "test"


def build_record(
    index: int,
    profile: dict[str, Any],
    query: str,
    source: str,
    generation_method: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "synthetic_id": f"syn_llm_{index:06d}",
        "user_query": query,
        "gold_model_id": profile["model_id"],
        "gold_model_name": profile["model_name"],
        "split": split_for_index(index),
        "intent_primary": "model_recommendation",
        "intent_domain": profile["domain"],
        "intent_task": profile.get("intent_task", "model_recommendation"),
        "expected_tags": profile.get("tags", []),
        "source": source,
        "annotation_version": ANNOTATION_VERSION,
        "generation_method": generation_method,
        "synthetic": True,
        "query_hash": stable_hash(normalize_text(query)),
        "needs_review": not validation["validation_passed"],
        "review_sample_required": True,
        "local_validation": validation,
    }


def generate_records(
    per_model: int,
    limit_models: int | None = None,
    dry_run_template: bool = False,
    llm_client: LLMClient | None = None,
    parser: DemandParser | None = None,
    temperature: float = 0.6,
) -> list[dict[str, Any]]:
    profiles = load_profiles(limit_models)
    if not profiles:
        raise RuntimeError("No official model profiles found.")

    client = llm_client or LLMClient()
    demand_parser = parser or DemandParser()
    if not dry_run_template and not client.available:
        return []

    source = DRY_RUN_SOURCE if dry_run_template else LIVE_SOURCE
    method = "template_dry_run" if dry_run_template else "llm_chat_completion"
    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for profile in profiles:
        requested_count = max(per_model + 5, int(per_model * 1.4))
        if dry_run_template:
            candidates = dry_run_queries(profile, requested_count)
        else:
            payload = client.chat_json(
                SYSTEM_PROMPT,
                build_user_prompt(profile, requested_count),
                temperature=temperature,
            )
            candidates = extract_queries(payload)

        generated_for_model = 0
        for query in candidates:
            q_hash = stable_hash(normalize_text(query))
            if q_hash in seen_hashes:
                continue
            validation = validate_query(query, profile, demand_parser)
            records.append(build_record(len(records) + 1, profile, query, source, method, validation))
            seen_hashes.add(q_hash)
            generated_for_model += 1
            if generated_for_model >= per_model:
                break

    return records


def build_manifest(records: list[dict[str, Any]], per_model: int, dry_run_template: bool) -> dict[str, Any]:
    model_counts = Counter(row["gold_model_id"] for row in records)
    source_counts = Counter(row["source"] for row in records)
    validation_counts = Counter(str(row["local_validation"]["validation_passed"]) for row in records)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_counts": dict(sorted(source_counts.items())),
        "annotation_version": ANNOTATION_VERSION,
        "generation_mode": "template_dry_run" if dry_run_template else "live_llm",
        "requested_per_model": per_model,
        "actual_total": len(records),
        "official_model_coverage": len(model_counts),
        "min_records_per_model": min(model_counts.values()) if model_counts else 0,
        "max_records_per_model": max(model_counts.values()) if model_counts else 0,
        "validation_passed_counts": dict(sorted(validation_counts.items())),
        "limitations": [
            "Live records require an externally configured LLM_API_KEY and are still synthetic development data.",
            "Dry-run records are template data and must not be described as LLM-generated.",
            "All records are isolated from official evaluation metrics.",
            "needs_review and local_validation support manual spot checks before training or demos.",
        ],
    }


def validate_records(records: list[dict[str, Any]], per_model: int, expected_models: int, dry_run_template: bool) -> None:
    if not records:
        raise RuntimeError("No records generated.")
    hashes = [row["query_hash"] for row in records]
    if len(hashes) != len(set(hashes)):
        raise RuntimeError("Duplicate normalized queries found.")
    model_counts = Counter(row["gold_model_id"] for row in records)
    if len(model_counts) != expected_models:
        raise RuntimeError(f"Expected coverage of {expected_models} models, got {len(model_counts)}")
    too_small = {model_id: count for model_id, count in model_counts.items() if count < per_model}
    if too_small:
        raise RuntimeError(f"Some models have fewer than {per_model} records: {list(too_small.items())[:5]}")
    expected_source = DRY_RUN_SOURCE if dry_run_template else LIVE_SOURCE
    bad_sources = {row["source"] for row in records if row["source"] != expected_source}
    if bad_sources:
        raise RuntimeError(f"Unexpected source labels: {sorted(bad_sources)}")


def resolve_output_path(path_text: str, dry_run_template: bool) -> Path:
    if path_text:
        return Path(path_text)
    filename = "synthetic_llm_dry_run_template.jsonl" if dry_run_template else "synthetic_llm_official_expansion.jsonl"
    return DEFAULT_OUTPUT_DIR / filename


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate LLM-enhanced synthetic development data.")
    parser.add_argument("--per-model", type=int, default=20, help="Records to keep for each official model.")
    parser.add_argument("--limit-models", type=int, default=0, help="Limit model count for smoke tests.")
    parser.add_argument("--output", default="", help="Output JSONL path.")
    parser.add_argument("--manifest", default="", help="Manifest JSON path.")
    parser.add_argument("--dry-run-template", action="store_true", help="Generate clearly labeled template dry-run data.")
    parser.add_argument("--temperature", type=float, default=0.6, help="LLM sampling temperature.")
    args = parser.parse_args()

    if args.per_model < 1:
        raise SystemExit("--per-model must be >= 1")

    client = LLMClient()
    if not args.dry_run_template and not client.available:
        status = client.status()
        safe_status = {
            "llm_enabled": status["llm_enabled"],
            "llm_provider": status["llm_provider"],
            "llm_model": status["llm_model"],
            "llm_base_url_configured": status["llm_base_url_configured"],
            "llm_api_key_configured": status["llm_api_key_configured"],
        }
        print(f"SKIP: live LLM generation requires configured environment. Status: {safe_status}")
        return 0

    limit_models = args.limit_models or None
    expected_models = limit_models or len(load_profiles(None))
    records = generate_records(
        per_model=args.per_model,
        limit_models=limit_models,
        dry_run_template=args.dry_run_template,
        llm_client=client,
        temperature=args.temperature,
    )
    validate_records(records, args.per_model, expected_models, args.dry_run_template)

    output_path = resolve_output_path(args.output, args.dry_run_template)
    manifest_path = Path(args.manifest) if args.manifest else output_path.with_suffix(".manifest.json")
    write_jsonl(output_path, records)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(build_manifest(records, args.per_model, args.dry_run_template), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    mode = "template dry-run" if args.dry_run_template else "live LLM"
    print(f"Generated {len(records)} {mode} records.")
    print(f"Output: {output_path}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
