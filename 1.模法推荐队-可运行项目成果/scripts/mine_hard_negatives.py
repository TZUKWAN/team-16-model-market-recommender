#!/usr/bin/env python3
"""Mine same-domain hard negatives from the official training split only."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.demand_parser import DemandParser
from app.services.recommender import ModelRecommendationService


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected an object")
            rows.append(row)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_hard_negatives(
    recommendations: list[Any],
    *,
    gold_model_id: str,
    model_domains: dict[str, str],
    limit: int,
) -> list[Any]:
    gold_domain = model_domains.get(gold_model_id, "")
    return [
        item
        for item in recommendations
        if item.model_id != gold_model_id and model_domains.get(item.model_id, "") == gold_domain
    ][:limit]


def mine(
    rows: list[dict[str, Any]],
    *,
    service: ModelRecommendationService,
    parser: DemandParser,
    negatives_per_case: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    non_train_ids = [str(row.get("test_id") or "") for row in rows if not str(row.get("test_id") or "").startswith("train_")]
    if non_train_ids:
        raise ValueError(f"hard-negative mining accepts train rows only: {non_train_ids[:5]}")

    model_domains = {
        str(model.get("model_id") or ""): str(model.get("domain") or "")
        for model in service.models
    }
    pairs: list[dict[str, Any]] = []
    gold_missing_top20 = 0
    dense_available_cases = 0

    for row in rows:
        test_id = str(row["test_id"])
        gold_id = str(row["gold_model_id"])
        query = str(row["query"])
        parsed = parser.parse(query, use_llm=False)
        payload = parsed.model_dump()
        payload["model_source"] = "official"
        result = service.recommend(
            payload,
            top_k=20,
            use_llm=False,
            use_llm_reason=False,
            use_keyword_rules=False,
            use_hybrid_retrieval=True,
        )
        dense_available_cases += int(bool(service.last_hybrid_retrieval_audit.get("dense_available")))
        rank_by_id = {item.model_id: item.rank for item in result.recommendations}
        score_by_id = {item.model_id: item.total_score for item in result.recommendations}
        gold_rank = rank_by_id.get(gold_id)
        if gold_rank is None:
            gold_missing_top20 += 1
        selected = select_hard_negatives(
            result.recommendations,
            gold_model_id=gold_id,
            model_domains=model_domains,
            limit=negatives_per_case,
        )
        for position, negative in enumerate(selected, start=1):
            gold_score = score_by_id.get(gold_id)
            pairs.append(
                {
                    "pair_id": f"{test_id}_hn{position}",
                    "source_test_id": test_id,
                    "source_split": "train",
                    "query": query,
                    "positive_model_id": gold_id,
                    "negative_model_id": negative.model_id,
                    "positive_rank_top20": gold_rank,
                    "negative_rank_top20": negative.rank,
                    "positive_score_top20": gold_score,
                    "negative_score_top20": negative.total_score,
                    "negative_outranks_positive": gold_rank is None or negative.rank < gold_rank,
                    "same_domain": True,
                    "training_use_only": True,
                    "mining_pipeline": {
                        "llm": False,
                        "keyword_rules": False,
                        "hybrid_retrieval": True,
                        "dense_enabled": bool(service.hybrid_config["dense_enabled"]),
                        "dense_weight": float(service.hybrid_config["dense_weight"]),
                        "dense_model": str(service.hybrid_config["dense_model"]),
                    },
                }
            )

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_split": "train",
        "source_case_count": len(rows),
        "pair_count": len(pairs),
        "negatives_per_case": negatives_per_case,
        "gold_missing_top20_count": gold_missing_top20,
        "negative_outranks_positive_count": sum(int(row["negative_outranks_positive"]) for row in pairs),
        "dense_available_case_count": dense_available_cases,
        "model_count": len(model_domains),
        "intended_use": "training_or_validation_design_only_not_official_metric_evidence",
    }
    return pairs, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine official-train hard negatives")
    parser.add_argument("--input", default="data/eval_official/topk_eval_official.jsonl")
    parser.add_argument("--output", default="data/training/hard_negative_pairs.jsonl")
    parser.add_argument("--metadata", default="data/training/hard_negative_pairs.metadata.json")
    parser.add_argument("--negatives-per-case", type=int, default=3)
    parser.add_argument("--dense-retrieval", choices=["off", "on"], default="off")
    parser.add_argument("--dense-weight", type=float, default=0.30)
    args = parser.parse_args()
    if args.negatives_per_case < 1:
        parser.error("--negatives-per-case must be positive")
    if not 0 <= args.dense_weight <= 1:
        parser.error("--dense-weight must be between 0 and 1")

    os.environ["HYBRID_DENSE_ENABLED"] = str(args.dense_retrieval == "on").lower()
    os.environ["HYBRID_DENSE_WEIGHT"] = str(args.dense_weight)
    input_path = (ROOT / args.input).resolve() if not Path(args.input).is_absolute() else Path(args.input)
    rows = [row for row in load_jsonl(input_path) if str(row.get("test_id") or "").startswith("train_")]
    service = ModelRecommendationService()
    pairs, metadata = mine(
        rows,
        service=service,
        parser=DemandParser(),
        negatives_per_case=args.negatives_per_case,
    )
    output_path = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    metadata_path = (ROOT / args.metadata).resolve() if not Path(args.metadata).is_absolute() else Path(args.metadata)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in pairs:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    metadata.update(
        {
            "source_file_sha256": sha256_file(input_path),
            "output_file_sha256": sha256_file(output_path),
        }
    )
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Mined {metadata['pair_count']} same-domain hard-negative pairs from "
        f"{metadata['source_case_count']} train cases"
    )


if __name__ == "__main__":
    main()
