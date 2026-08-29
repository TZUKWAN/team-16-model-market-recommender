#!/usr/bin/env python3
"""Freeze, validate, and evaluate an independently authored blind set.

The public case file never contains gold labels. The private label file is
gitignored and must be independently reviewed before this tool will freeze or
evaluate it as formal evidence.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.demand_parser import DemandParser
from app.services.recommender import ModelRecommendationService


ALLOWED_SCENARIOS = {"credit_risk", "customer_marketing", "operation_management"}
FORBIDDEN_CASE_FIELDS = {
    "gold_model_id",
    "gold_model_ids",
    "gold_model_name",
    "gold_model_names",
    "expected_model_ids",
    "acceptable_model_ids",
    "primary_model_id",
}
CASE_ATTESTATION = "independent_human_authored"
LABEL_ATTESTATION = "independent_human_review"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: each line must be an object")
            rows.append(row)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _unique_index(rows: list[dict[str, Any]], key: str, errors: list[str], kind: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows, start=1):
        value = str(row.get(key) or "").strip()
        if not value:
            errors.append(f"{kind} row {index}: missing {key}")
        elif value in result:
            errors.append(f"{kind}: duplicate {key} {value}")
        else:
            result[value] = row
    return result


def load_official_reference() -> tuple[list[str], dict[str, str]]:
    questions = load_jsonl(ROOT / "data" / "eval_official" / "topk_eval_official.jsonl")
    models = load_jsonl(ROOT / "data" / "official" / "model_catalog_structured.jsonl")
    return (
        [str(row.get("query") or "") for row in questions if row.get("query")],
        {
            str(row.get("model_id") or ""): str(
                row.get("canonical_name") or row.get("model_name") or ""
            )
            for row in models
            if row.get("model_id")
        },
    )


def near_duplicate_stats(
    blind_queries: list[str], official_queries: list[str], threshold: float
) -> dict[str, Any]:
    if not blind_queries or not official_queries:
        return {"threshold": threshold, "count": 0, "max_similarity": 0.0, "mean_max_similarity": 0.0}
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 5), sublinear_tf=True, norm="l2")
    matrix = vectorizer.fit_transform(official_queries + blind_queries)
    official_matrix = matrix[: len(official_queries)]
    blind_matrix = matrix[len(official_queries) :]
    similarities = cosine_similarity(blind_matrix, official_matrix)
    maxima = np.max(similarities, axis=1)
    return {
        "threshold": threshold,
        "count": int(np.sum(maxima >= threshold)),
        "max_similarity": round(float(np.max(maxima)), 6),
        "mean_max_similarity": round(float(np.mean(maxima)), 6),
        "per_case_max_similarity": [round(float(value), 6) for value in maxima],
    }


def validate_blind_dataset(
    cases: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    *,
    official_queries: list[str],
    model_names: dict[str, str],
    near_duplicate_threshold: float = 0.92,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    case_by_id = _unique_index(cases, "case_id", errors, "case")
    label_by_id = _unique_index(labels, "case_id", errors, "label")

    if not cases:
        errors.append("case file is empty")
    if not labels:
        errors.append("label file is empty")
    if set(case_by_id) != set(label_by_id):
        missing_labels = sorted(set(case_by_id) - set(label_by_id))
        extra_labels = sorted(set(label_by_id) - set(case_by_id))
        if missing_labels:
            errors.append(f"cases without labels: {missing_labels[:10]}")
        if extra_labels:
            errors.append(f"labels without cases: {extra_labels[:10]}")

    normalized_official = {normalize_text(query) for query in official_queries if normalize_text(query)}
    normalized_blind: list[str] = []
    query_seen: set[str] = set()
    model_name_tokens = [
        (model_id, normalize_text(name))
        for model_id, name in model_names.items()
        if len(normalize_text(name)) >= 6
    ]

    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("case_id") or "").strip() or f"row-{index}"
        query = str(case.get("query") or "").strip()
        author_id = str(case.get("author_id") or "").strip()
        scenario = str(case.get("scenario") or "").strip()
        if not query:
            errors.append(f"{case_id}: missing query")
        if not author_id:
            errors.append(f"{case_id}: missing author_id")
        if scenario not in ALLOWED_SCENARIOS:
            errors.append(f"{case_id}: invalid scenario {scenario!r}")
        if case.get("authorship_attestation") != CASE_ATTESTATION:
            errors.append(f"{case_id}: missing human authorship attestation")
        leaked_fields = sorted(FORBIDDEN_CASE_FIELDS & set(case))
        if leaked_fields:
            errors.append(f"{case_id}: public case leaks label fields {leaked_fields}")
        normalized = normalize_text(query)
        normalized_blind.append(normalized)
        if normalized in query_seen:
            errors.append(f"{case_id}: duplicate blind query")
        query_seen.add(normalized)
        if normalized and normalized in normalized_official:
            errors.append(f"{case_id}: exact duplicate of an official evaluation query")
        if re.search(r"\b(?:OFFICIAL|RISK|MKT|OPS)_?\d+\b", query, flags=re.IGNORECASE):
            errors.append(f"{case_id}: query contains a model ID")
        leaked_names = [model_id for model_id, token in model_name_tokens if token and token in normalized]
        if leaked_names:
            errors.append(f"{case_id}: query contains an exact catalog model name ({leaked_names[:3]})")

    valid_model_ids = set(model_names)
    for case_id, label in label_by_id.items():
        acceptable = label.get("acceptable_model_ids")
        primary = str(label.get("primary_model_id") or "").strip()
        reviewer_id = str(label.get("reviewer_id") or "").strip()
        if not isinstance(acceptable, list) or not acceptable:
            errors.append(f"{case_id}: acceptable_model_ids must be a non-empty list")
            acceptable_ids: list[str] = []
        else:
            acceptable_ids = [str(value).strip() for value in acceptable if str(value).strip()]
        invalid_ids = sorted(set(acceptable_ids) - valid_model_ids)
        if invalid_ids:
            errors.append(f"{case_id}: unknown acceptable model IDs {invalid_ids}")
        if primary not in acceptable_ids:
            errors.append(f"{case_id}: primary_model_id must be acceptable")
        if not reviewer_id:
            errors.append(f"{case_id}: missing reviewer_id")
        author_id = str(case_by_id.get(case_id, {}).get("author_id") or "").strip()
        if reviewer_id and reviewer_id == author_id:
            errors.append(f"{case_id}: author and reviewer must be different people")
        if label.get("review_status") != "approved":
            errors.append(f"{case_id}: review_status must be approved")
        if label.get("review_attestation") != LABEL_ATTESTATION:
            errors.append(f"{case_id}: missing independent review attestation")

    near = near_duplicate_stats(
        [query for query in normalized_blind if query],
        [normalize_text(query) for query in official_queries if normalize_text(query)],
        near_duplicate_threshold,
    )
    if near["count"]:
        errors.append(
            f"{near['count']} blind queries exceed official near-duplicate threshold "
            f"{near_duplicate_threshold}"
        )
    if len(cases) < 150:
        warnings.append("formal competition evidence should contain at least 150 blind cases")

    primary_counts: dict[str, int] = defaultdict(int)
    scenario_counts: dict[str, int] = defaultdict(int)
    for case in cases:
        scenario_counts[str(case.get("scenario") or "unknown")] += 1
    for label in labels:
        primary_counts[str(label.get("primary_model_id") or "unknown")] += 1

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "case_count": len(cases),
        "label_count": len(labels),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "primary_model_count": len(primary_counts),
        "primary_model_case_counts": dict(sorted(primary_counts.items())),
        "near_duplicate": near,
    }


def create_manifest(
    cases_path: Path,
    labels_path: Path,
    manifest_path: Path,
    validation: dict[str, Any],
) -> dict[str, Any]:
    if not validation.get("valid"):
        raise ValueError("blind dataset failed validation and cannot be frozen")
    cases = load_jsonl(cases_path)
    case_ids = [str(row["case_id"]) for row in cases]
    manifest = {
        "manifest_version": 1,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "cases": {
            "file_name": cases_path.name,
            "sha256": sha256_file(cases_path),
            "count": len(cases),
        },
        "private_labels": {
            "file_name": labels_path.name,
            "sha256": sha256_file(labels_path),
            "count": len(load_jsonl(labels_path)),
            "committed_to_repository": False,
        },
        "case_id_order_sha256": hashlib.sha256(
            "\n".join(case_ids).encode("utf-8")
        ).hexdigest(),
        "policy": {
            "keyword_rules": False,
            "author_reviewer_separation": True,
            "model_identity_leakage": False,
            "official_near_duplicate_threshold": validation["near_duplicate"]["threshold"],
        },
        "validation_summary": {
            "scenario_counts": validation["scenario_counts"],
            "primary_model_count": validation["primary_model_count"],
            "warnings": validation["warnings"],
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(cases_path: Path, labels_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    expected_cases = str(manifest.get("cases", {}).get("sha256") or "")
    expected_labels = str(manifest.get("private_labels", {}).get("sha256") or "")
    if sha256_file(cases_path) != expected_cases:
        raise ValueError("public case file changed after freeze")
    if sha256_file(labels_path) != expected_labels:
        raise ValueError("private label file changed after freeze")
    return manifest


def evaluate_blind_set(
    cases: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    *,
    parser_use_llm: bool,
    rerank_use_llm: bool,
) -> dict[str, Any]:
    parser = DemandParser()
    recommender = ModelRecommendationService()
    if (parser_use_llm and not parser.llm.available) or (rerank_use_llm and not recommender.llm.available):
        raise RuntimeError("live LLM was requested but is not available")

    labels_by_id = {str(row["case_id"]): row for row in labels}
    top3_hits = 0
    top5_hits = 0
    per_model: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    per_scenario: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    trace_ids: set[str] = set()
    dense_available = 0
    details: list[dict[str, Any]] = []

    for case in cases:
        case_id = str(case["case_id"])
        query = str(case["query"])
        label = labels_by_id[case_id]
        acceptable = set(str(value) for value in label["acceptable_model_ids"])
        primary = str(label["primary_model_id"])
        parsed = parser.parse(query, use_llm=parser_use_llm)
        parse_trace = str(getattr(parsed, "llm_trace_id", "") or "")
        if parse_trace:
            trace_ids.add(parse_trace)
        payload = parsed.model_dump()
        payload["model_source"] = "official"
        result = recommender.recommend(
            payload,
            top_k=5,
            use_llm=rerank_use_llm,
            use_llm_reason=False,
            use_keyword_rules=False,
            use_hybrid_retrieval=True,
        )
        recommended = [item.model_id for item in result.recommendations]
        hit3 = bool(acceptable & set(recommended[:3]))
        hit5 = bool(acceptable & set(recommended[:5]))
        top3_hits += int(hit3)
        top5_hits += int(hit5)
        per_model[primary].append((hit3, hit5))
        per_scenario[str(case["scenario"])].append((hit3, hit5))
        rerank_audit = dict(recommender.last_llm_rerank_audit)
        trace_ids.update(str(value) for value in rerank_audit.get("trace_ids") or [] if value)
        retrieval_audit = dict(recommender.last_hybrid_retrieval_audit)
        dense_available += int(bool(retrieval_audit.get("dense_available")))
        details.append(
            {
                "case_id": case_id,
                "recommended_top5_ids": recommended,
                "acceptable_model_ids": sorted(acceptable),
                "primary_model_id": primary,
                "top3_hit": hit3,
                "top5_hit": hit5,
                "parse_source": parsed.parse_source,
                "parser_trace_id": parse_trace,
                "rerank_audit": rerank_audit,
                "hybrid_retrieval_audit": retrieval_audit,
            }
        )

    total = len(cases)

    def rates(groups: dict[str, list[tuple[bool, bool]]]) -> dict[str, Any]:
        return {
            key: {
                "count": len(values),
                "top3_pct": round(sum(int(a) for a, _ in values) / len(values) * 100, 2),
                "top5_pct": round(sum(int(b) for _, b in values) / len(values) * 100, 2),
            }
            for key, values in sorted(groups.items())
        }

    model_rates = rates(per_model)
    macro_top3 = round(sum(value["top3_pct"] for value in model_rates.values()) / len(model_rates), 2)
    macro_top5 = round(sum(value["top5_pct"] for value in model_rates.values()) / len(model_rates), 2)
    return {
        "metric": "independent_blind_topk",
        "total": total,
        "micro_top3_pct": round(top3_hits / total * 100, 2),
        "micro_top5_pct": round(top5_hits / total * 100, 2),
        "macro_by_primary_model_top3_pct": macro_top3,
        "macro_by_primary_model_top5_pct": macro_top5,
        "per_model": model_rates,
        "per_scenario": rates(per_scenario),
        "pipeline": {
            "keyword_rules": False,
            "parser_use_llm": parser_use_llm,
            "rerank_use_llm": rerank_use_llm,
            "dense_enabled": bool(recommender.hybrid_config["dense_enabled"]),
            "dense_weight": float(recommender.hybrid_config["dense_weight"]),
            "dense_model": str(recommender.hybrid_config["dense_model"]),
        },
        "evidence": {
            "trace_count": len(trace_ids),
            "dense_available_case_count": dense_available,
            "dense_case_coverage_pct": round(dense_available / total * 100, 2),
        },
        "details": details,
    }


def build_blind_report(
    *,
    manifest_path: Path,
    cases_path: Path,
    labels_path: Path,
    validation: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    """Build an honest report without claiming software verified human identity."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blind_software_gate_passed": True,
        "formal_blind_evidence": False,
        "formal_evidence_status": "requires_external_human_identity_and_review_record_verification",
        "software_verification_boundary": (
            "the tool validates declared IDs, attestations, separation, leakage, overlap, and hashes; "
            "it cannot prove that declared author and reviewer IDs belong to different real people"
        ),
        "manifest_sha256": sha256_file(manifest_path),
        "case_sha256": sha256_file(cases_path),
        "private_label_sha256": sha256_file(labels_path),
        "validation": validation,
        "evaluation": evaluation,
    }


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return Path(args.cases).resolve(), Path(args.labels).resolve(), Path(args.manifest).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent blind evaluation gate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("validate", "freeze", "evaluate"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--cases", required=True, help="Public unlabeled JSONL")
        sub.add_argument("--labels", required=True, help="Private reviewed labels JSONL")
        sub.add_argument("--manifest", required=True, help="Frozen manifest JSON")
        sub.add_argument("--near-duplicate-threshold", type=float, default=0.92)

    evaluate = subparsers.choices["evaluate"]
    evaluate.add_argument("--llm-mode", choices=["off", "on"], default="off")
    evaluate.add_argument("--llm-scope", choices=["parser", "rerank", "both"], default="rerank")
    evaluate.add_argument("--dense-retrieval", choices=["config", "off", "on"], default="config")
    evaluate.add_argument("--dense-weight", type=float, default=None)
    evaluate.add_argument("--output", required=True, help="Private result JSON path")

    args = parser.parse_args()
    if not 0 < args.near_duplicate_threshold <= 1:
        parser.error("--near-duplicate-threshold must be in (0, 1]")
    cases_path, labels_path, manifest_path = _paths(args)
    cases = load_jsonl(cases_path)
    labels = load_jsonl(labels_path)
    official_queries, model_names = load_official_reference()
    validation = validate_blind_dataset(
        cases,
        labels,
        official_queries=official_queries,
        model_names=model_names,
        near_duplicate_threshold=args.near_duplicate_threshold,
    )
    if not validation["valid"]:
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    if args.command == "validate":
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return
    if args.command == "freeze":
        manifest = create_manifest(cases_path, labels_path, manifest_path, validation)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return

    verify_manifest(cases_path, labels_path, manifest_path)
    if args.dense_weight is not None and not 0 <= args.dense_weight <= 1:
        parser.error("--dense-weight must be between 0 and 1")
    if args.dense_retrieval != "config":
        os.environ["HYBRID_DENSE_ENABLED"] = str(args.dense_retrieval == "on").lower()
    if args.dense_weight is not None:
        os.environ["HYBRID_DENSE_WEIGHT"] = str(args.dense_weight)
    llm_on = args.llm_mode == "on"
    result = evaluate_blind_set(
        cases,
        labels,
        parser_use_llm=llm_on and args.llm_scope in {"parser", "both"},
        rerank_use_llm=llm_on and args.llm_scope in {"rerank", "both"},
    )
    report = build_blind_report(
        manifest_path=manifest_path,
        cases_path=cases_path,
        labels_path=labels_path,
        validation=validation,
        evaluation=result,
    )
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Blind evaluation complete: Top3={result['micro_top3_pct']}%, "
        f"Top5={result['micro_top5_pct']}%, cases={result['total']}"
    )


if __name__ == "__main__":
    main()
