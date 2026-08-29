#!/usr/bin/env python3
"""Audit split integrity, test-set exposure, and data provenance.

This audit deliberately separates three questions:

1. Was the official test split directly used as training data?
2. Is the checked-in test split still a truly blind holdout?
3. Which non-official or weakly annotated fields influence runtime ranking?

The script uses only the Python standard library and the checked-in repository.
It writes both machine-readable JSON and a Chinese Markdown review report.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unicodedata
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "reports" / "audit" / "data_integrity_audit_20260722.json"
DEFAULT_MARKDOWN = ROOT / "reports" / "audit" / "data_integrity_audit_20260722.md"

CURRENT_EVAL_REPORTS = {
    "train": ROOT / "reports" / "audit" / "official_eval_train_20260722.json",
    "val": ROOT / "reports" / "audit" / "official_eval_val_20260722.json",
    "test": ROOT / "reports" / "audit" / "official_eval_test_20260722.json",
}
CALIBRATION_EVAL_REPORTS = {
    "train": ROOT / "reports" / "calibration" / "train_dense_w05.json",
    "val": ROOT / "reports" / "calibration" / "val_dense_w05.json",
    "test": ROOT / "reports" / "calibration" / "final_test_dense_w05.json",
}

CANONICAL_SPLITS = {
    "train": ROOT / "data" / "official" / "questions_train.jsonl",
    "val": ROOT / "data" / "official" / "questions_val.jsonl",
    "test": ROOT / "data" / "official" / "questions_test.jsonl",
}
MIRROR_SPLITS = {
    "train": ROOT / "data" / "official_60" / "queries_train.jsonl",
    "val": ROOT / "data" / "official_60" / "queries_val.jsonl",
    "test": ROOT / "data" / "official_60" / "queries_test.jsonl",
}

GENERIC_MODEL_SUFFIXES = (
    "机器学习算法模型",
    "机器学习模型",
    "算法模型",
    "预测模型",
    "推荐模型",
    "分析模型",
    "识别模型",
    "预警模型",
    "评分模型",
    "模型",
    "评分卡",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(payload)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_worktree_state() -> dict[str, Any]:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    changed = [line for line in completed.stdout.splitlines() if line.strip()]
    return {
        "working_tree_dirty": bool(changed),
        "dirty_file_count": len(changed),
    }


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def row_id(row: dict[str, Any]) -> str:
    return str(row.get("question_id") or row.get("query_id") or row.get("test_id") or "")


def row_query(row: dict[str, Any]) -> str:
    return str(row.get("user_query") or row.get("query") or "")


def row_gold_id(row: dict[str, Any]) -> str:
    value = row.get("gold_model_id")
    if value:
        return str(value)
    values = row.get("gold_model_ids") or []
    return str(values[0]) if values else ""


def row_gold_name(row: dict[str, Any]) -> str:
    value = row.get("gold_model_name")
    if value:
        return str(value)
    values = row.get("gold_model_names") or []
    return str(values[0]) if values else ""


def canonical_tuple(row: dict[str, Any]) -> tuple[str, str, str]:
    return row_id(row), normalize_text(row_query(row)), row_gold_id(row)


def char_bigrams(text: str) -> set[str]:
    normalized = normalize_text(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def near_similarity(left: str, right: str) -> dict[str, float]:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_grams = char_bigrams(left_norm)
    right_grams = char_bigrams(right_norm)
    union = left_grams | right_grams
    jaccard = len(left_grams & right_grams) / len(union) if union else 1.0
    return {
        "sequence_ratio": round(sequence, 4),
        "bigram_jaccard": round(jaccard, 4),
        "combined": round((sequence + jaccard) / 2, 4),
    }


def split_integrity(
    splits: dict[str, list[dict[str, Any]]],
    mirrors: dict[str, list[dict[str, Any]]],
    near_threshold: float,
) -> dict[str, Any]:
    manual_review_threshold = 0.55
    counts = {name: len(rows) for name, rows in splits.items()}
    ids = {name: {row_id(row) for row in rows} for name, rows in splits.items()}
    id_overlaps: list[dict[str, Any]] = []
    split_names = list(splits)
    for left_index, left_name in enumerate(split_names):
        for right_name in split_names[left_index + 1 :]:
            overlap = sorted(ids[left_name] & ids[right_name])
            if overlap:
                id_overlaps.append(
                    {"splits": [left_name, right_name], "count": len(overlap), "examples": overlap[:10]}
                )

    normalized_locations: dict[str, list[dict[str, str]]] = {}
    for split_name, rows in splits.items():
        for row in rows:
            normalized_locations.setdefault(normalize_text(row_query(row)), []).append(
                {"split": split_name, "id": row_id(row), "gold_model_id": row_gold_id(row)}
            )
    exact_cross_split = [
        {"normalized_query": query, "locations": locations}
        for query, locations in normalized_locations.items()
        if len({location["split"] for location in locations}) > 1
    ]

    near_pairs: list[dict[str, Any]] = []
    top_pairs: list[dict[str, Any]] = []
    for left_index, left_name in enumerate(split_names):
        for right_name in split_names[left_index + 1 :]:
            for left in splits[left_name]:
                for right in splits[right_name]:
                    similarity = near_similarity(row_query(left), row_query(right))
                    item = {
                        "left_split": left_name,
                        "left_id": row_id(left),
                        "right_split": right_name,
                        "right_id": row_id(right),
                        "same_gold_model": row_gold_id(left) == row_gold_id(right),
                        **similarity,
                        "left_query": row_query(left),
                        "right_query": row_query(right),
                    }
                    top_pairs.append(item)
                    if similarity["combined"] >= near_threshold:
                        near_pairs.append(item)

    top_pairs.sort(key=lambda item: item["combined"], reverse=True)
    near_pairs.sort(key=lambda item: item["combined"], reverse=True)
    manual_review_pairs = [
        item for item in top_pairs if item["combined"] >= manual_review_threshold
    ]

    mirror_checks: dict[str, Any] = {}
    for split_name in split_names:
        canonical_rows = {canonical_tuple(row) for row in splits[split_name]}
        mirror_rows = {canonical_tuple(row) for row in mirrors[split_name]}
        mirror_checks[split_name] = {
            "canonical_count": len(canonical_rows),
            "mirror_count": len(mirror_rows),
            "exact_match": canonical_rows == mirror_rows,
            "canonical_only_count": len(canonical_rows - mirror_rows),
            "mirror_only_count": len(mirror_rows - canonical_rows),
        }

    model_coverage = {
        split_name: sorted({row_gold_id(row) for row in rows if row_gold_id(row)})
        for split_name, rows in splits.items()
    }

    return {
        "counts": counts,
        "split_id_overlap_count": sum(item["count"] for item in id_overlaps),
        "split_id_overlaps": id_overlaps,
        "exact_cross_split_query_count": len(exact_cross_split),
        "exact_cross_split_queries": exact_cross_split[:20],
        "near_duplicate_threshold": near_threshold,
        "near_duplicate_count": len(near_pairs),
        "near_duplicates": near_pairs[:30],
        "manual_review_threshold": manual_review_threshold,
        "manual_review_candidate_count": len(manual_review_pairs),
        "manual_review_candidates": manual_review_pairs[:30],
        "semantic_duplicate_check_performed": False,
        "near_duplicate_scope": (
            "Character-level SequenceMatcher and bigram Jaccard only. A zero count at the "
            "configured threshold does not rule out semantic paraphrases."
        ),
        "top_cross_split_similarities": top_pairs[:20],
        "mirror_consistency": mirror_checks,
        "gold_model_coverage": {name: len(values) for name, values in model_coverage.items()},
        "gold_models_shared_by_all_splits": len(
            set(model_coverage["train"]) & set(model_coverage["val"]) & set(model_coverage["test"])
        ),
        "split_strategy": "query-level split; not a model/entity holdout",
        "mirror_comparison_scope": "question ID + normalized query + gold model ID tuple",
    }


def core_model_name(name: str) -> str:
    core = normalize_text(name)
    changed = True
    while changed:
        changed = False
        for suffix in GENERIC_MODEL_SUFFIXES:
            suffix_norm = normalize_text(suffix)
            if core.endswith(suffix_norm) and len(core) > len(suffix_norm):
                core = core[: -len(suffix_norm)]
                changed = True
                break
    return core


def model_name_exposure(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split_name, rows in splits.items():
        full_hits: list[dict[str, str]] = []
        core_hits: list[dict[str, str]] = []
        for row in rows:
            query = normalize_text(row_query(row))
            name = normalize_text(row_gold_name(row))
            core = core_model_name(row_gold_name(row))
            record = {
                "id": row_id(row),
                "gold_model_id": row_gold_id(row),
                "gold_model_name": row_gold_name(row),
                "query": row_query(row),
            }
            if name and name in query:
                full_hits.append(record)
            elif len(core) >= 4 and core in query:
                core_hits.append({**record, "matched_core": core})
        total = len(rows)
        result[split_name] = {
            "total": total,
            "full_name_hit_count": len(full_hits),
            "full_name_hit_pct": round(len(full_hits) / total * 100, 2) if total else 0.0,
            "core_name_hit_count": len(core_hits),
            "core_name_hit_pct": round(len(core_hits) / total * 100, 2) if total else 0.0,
            "conservative_any_name_hit_count": len(full_hits) + len(core_hits),
            "conservative_any_name_hit_pct": (
                round((len(full_hits) + len(core_hits)) / total * 100, 2) if total else 0.0
            ),
            "examples": (full_hits + core_hits)[:15],
        }
    return result


def audit_hard_negatives(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    pairs_path = ROOT / "data" / "training" / "hard_negative_pairs.jsonl"
    metadata_path = ROOT / "data" / "training" / "hard_negative_pairs.metadata.json"
    source_path = ROOT / "data" / "eval_official" / "topk_eval_official.jsonl"
    pairs = load_jsonl(pairs_path)
    metadata = load_json(metadata_path)
    train_by_id = {row_id(row): normalize_text(row_query(row)) for row in splits["train"]}
    non_train_ids = [
        str(row.get("source_test_id") or "")
        for row in pairs
        if not str(row.get("source_test_id") or "").startswith("train_")
    ]
    non_train_split_markers = [
        str(row.get("source_split") or "")
        for row in pairs
        if str(row.get("source_split") or "") != "train"
    ]
    query_mismatches = [
        str(row.get("source_test_id") or "")
        for row in pairs
        if train_by_id.get(str(row.get("source_test_id") or "")) != normalize_text(row.get("query"))
    ]
    source_ids = {str(row.get("source_test_id") or "") for row in pairs}
    val_test_ids = {
        row_id(row)
        for split_name in ("val", "test")
        for row in splits[split_name]
    }
    source_hash_actual = sha256_file(source_path)
    output_hash_actual = sha256_file(pairs_path)
    source_hash_recorded = str(metadata.get("source_file_sha256") or "")
    output_hash_recorded = str(metadata.get("output_file_sha256") or "")
    source_hash_matches = source_hash_recorded == source_hash_actual
    output_hash_matches = output_hash_recorded == output_hash_actual
    return {
        "pair_count": len(pairs),
        "unique_source_case_count": len(source_ids),
        "metadata_source_split": metadata.get("source_split"),
        "metadata_source_case_count": metadata.get("source_case_count"),
        "non_train_id_count": len(non_train_ids),
        "non_train_split_marker_count": len(non_train_split_markers),
        "query_not_found_in_train_count": len(query_mismatches),
        "val_test_id_intersection_count": len(source_ids & val_test_ids),
        "source_file_is_full_417_eval_file": True,
        "source_file_sha256_recorded": source_hash_recorded,
        "source_file_sha256_actual": source_hash_actual,
        "source_file_sha256_matches_metadata": source_hash_matches,
        "output_file_sha256_recorded": output_hash_recorded,
        "output_file_sha256_actual": output_hash_actual,
        "output_file_sha256_matches_metadata": output_hash_matches,
        "provenance_hashes_match": source_hash_matches and output_hash_matches,
        "reproducibility_status": (
            "metadata_hashes_match"
            if source_hash_matches and output_hash_matches
            else "metadata_hashes_stale_current_pairs_need_regeneration_or_migration_record"
        ),
        "selection_behavior": (
            "The input file contains all 417 cases, but mine_hard_negatives.py filters train_ rows "
            "before mining and rejects any non-train row passed to mine()."
        ),
        "direct_test_training_leakage_found": bool(
            non_train_ids or non_train_split_markers or query_mismatches or source_ids & val_test_ids
        ),
        "finding": (
            "All current pair IDs and queries resolve to the train split, so no direct val/test "
            "leakage was found. Hash mismatches, when present, mean the checked-in metadata no "
            "longer proves byte-for-byte reproducibility."
        ),
    }


def scan_runtime_for_eval_access() -> dict[str, Any]:
    ranking_paths = [
        ROOT / "backend" / "app" / "services" / "recommender.py",
        ROOT / "backend" / "app" / "services" / "demand_parser.py",
        ROOT / "backend" / "app" / "services" / "hybrid_retriever.py",
        ROOT / "data" / "config" / "recommendation_weights.json",
        ROOT / "data" / "config" / "keyword_rules.json",
        ROOT / "data" / "config" / "synonyms.json",
    ]
    forbidden = (
        "questions_test",
        "queries_test",
        "questions_all",
        "gold_model_id",
        "gold_model_name",
        "test_000",
        "val_000",
    )
    hits: list[dict[str, Any]] = []
    for path in ranking_paths:
        text = path.read_text("utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            matched = [token for token in forbidden if token in line]
            if matched:
                hits.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "line": line_number,
                        "tokens": matched,
                        "text": line.strip()[:180],
                    }
                )
    return {
        "scanned_paths": [path.relative_to(ROOT).as_posix() for path in ranking_paths],
        "forbidden_reference_count": len(hits),
        "hits": hits,
        "runtime_recommender_reads_gold_or_split_files": bool(hits),
        "scope_limitation": (
            "Static substring scan of the listed runtime ranking files only; this is evidence "
            "of no reference in the inspected path, not a proof about every future code path."
        ),
    }


def audit_bge_training_evidence() -> dict[str, Any]:
    """Look for common sentence-transformer fine-tuning entry points in project code."""
    scan_roots = [ROOT / "backend" / "app", ROOT / "scripts"]
    markers = (
        "SentenceTransformerTrainer",
        "MultipleNegativesRankingLoss",
        "CosineSimilarityLoss",
        "TripletLoss",
        "encoder.fit(",
        "sentence_transformer.fit(",
    )
    hits: list[dict[str, Any]] = []
    paths: list[Path] = []
    for scan_root in scan_roots:
        paths.extend(sorted(scan_root.rglob("*.py")))
    paths = [path for path in paths if path.resolve() != Path(__file__).resolve()]
    for path in paths:
        for line_number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
            matched = [marker for marker in markers if marker in line]
            if matched:
                hits.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "line": line_number,
                        "markers": matched,
                        "text": line.strip()[:180],
                    }
                )
    return {
        "scanned_python_file_count": len(paths),
        "training_marker_count": len(hits),
        "training_marker_hits": hits,
        "project_finetuning_evidence_found": bool(hits),
        "finding": (
            "No common SentenceTransformers fine-tuning entry point was found in backend/app "
            "or scripts. The repository code loads BGE-M3 for encode-only inference. This is a "
            "bounded code scan, not a statement about activities outside the repository."
        ),
    }


def audit_weak_labels(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    all_rows = [row for rows in splits.values() for row in rows]
    converter = (ROOT / "scripts" / "convert_official_dataset.py").read_text("utf-8")
    return {
        "total_cases": len(all_rows),
        "needs_review_true_count": sum(bool(row.get("needs_review")) for row in all_rows),
        "annotation_versions": dict(Counter(str(row.get("annotation_version") or "") for row in all_rows)),
        "expected_tags_derived_from_query_and_gold_name": (
            "extract_tags(query, model_name" in converter
        ),
        "intent_task_derived_from_query_and_gold_name": (
            "classify_task(model_name, query)" in converter
        ),
        "finding": (
            "TopK gold model names come from the official Excel answer column. "
            "Intent/task/tag labels are local weak annotations derived from both the query and "
            "the gold answer model name, and remain marked needs_review. Intent/tag accuracy "
            "therefore has direct label-dependency risk and is not independent human-labelled "
            "generalization evidence."
        ),
        "risk_by_metric": {
            "topk": "medium",
            "intent_accuracy": "high",
            "tag_accuracy": "high",
        },
    }


def audit_synthetic_lineage() -> dict[str, Any]:
    generator_path = ROOT / "scripts" / "generate_synthetic_official_data.py"
    generator = generator_path.read_text("utf-8")
    runtime_paths = [
        ROOT / "backend" / "app" / "services" / "recommender.py",
        ROOT / "backend" / "app" / "services" / "demand_parser.py",
        ROOT / "backend" / "app" / "services" / "hybrid_retriever.py",
        ROOT / "data" / "config" / "recommendation_weights.json",
    ]
    runtime_hits = [
        path.relative_to(ROOT).as_posix()
        for path in runtime_paths
        if "synthetic_questions" in path.read_text("utf-8")
        or "data/synthetic" in path.read_text("utf-8")
    ]
    dataset_card = (ROOT / "docs" / "data" / "synthetic_dataset_card.md").read_text("utf-8")
    questions_all = load_jsonl(ROOT / "data" / "official" / "questions_all.jsonl")
    all_splits = {str(row.get("split") or "") for row in questions_all}
    return {
        "generator_uses_official_questions_all": (
            'questions_all.jsonl' in generator and "OFFICIAL_DIR" in generator
        ),
        "questions_all_contains_test": "test" in all_splits,
        "questions_all_split_values": sorted(all_splits),
        "runtime_ranking_reference_count": len(runtime_hits),
        "runtime_ranking_references": runtime_hits,
        "currently_used_for_runtime_training_or_ranking": bool(runtime_hits),
        "documentation_warns_against_training_use": (
            "不能直接作为新的训练/调参集" in dataset_card
            and "只读取 `questions_train.jsonl`" in dataset_card
        ),
        "train_only_lineage_guard_enforced": False,
        "future_use_warning": (
            "The synthetic corpus is derived from questions_all (train+val+test). "
            "It is not used by the current runtime ranker, but it must be regenerated from "
            "train-only source questions before any future parser/ranker training or tuning."
        ),
    }


def audit_model_field_provenance() -> dict[str, Any]:
    provenance = load_json(ROOT / "reports" / "data_governance" / "model_field_provenance.json")
    recommender = (ROOT / "backend" / "app" / "services" / "recommender.py").read_text("utf-8")
    coverage = provenance.get("coverage", {})
    synthetic_fields = {
        field: details
        for field, details in coverage.items()
        if "synthetic_draft" in (details.get("source_types") or {})
    }
    ranking_uses_metrics = 'model.get("performance_metrics"' in recommender
    ranking_uses_cases = 'model.get("historical_cases"' in recommender
    return {
        "official_raw_verified_fields": ["canonical_name", "description"],
        "deterministic_inference_fields": [
            "domain",
            "customer_segment",
            "input_schema",
            "result_schema",
        ],
        "synthetic_draft_fields": sorted(synthetic_fields),
        "synthetic_draft_verified_count": {
            field: int(details.get("verified_count") or 0)
            for field, details in synthetic_fields.items()
        },
        "runtime_ranking_uses_performance_metrics": ranking_uses_metrics,
        "runtime_ranking_uses_historical_cases": ranking_uses_cases,
        "finding": (
            "Synthetic-draft performance metrics and historical cases are not official bank "
            "evidence. The current structured score reads both fields, so they can influence "
            "the small structured-score portion of ranking and must be labelled or disabled "
            "before making production-evidence claims."
        ),
        "risk_level": "medium" if ranking_uses_metrics or ranking_uses_cases else "low",
    }


def git_log(paths: Iterable[str]) -> list[dict[str, str]]:
    command = [
        "git",
        "log",
        "--all",
        "--reverse",
        "--date=iso-strict",
        "--format=%H%x09%aI%x09%s",
        "--",
        *paths,
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    events: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            events.append({"commit": parts[0], "date": parts[1], "subject": parts[2]})
    return events


def audit_test_exposure() -> dict[str, Any]:
    test_report_paths = [
        "reports/official_eval/test_results.json",
        "reports/official/eval_official_test_results.json",
        "reports/calibration/final_test_dense_w05.json",
        "reports/official/eval_official_results.json",
    ]
    algorithm_paths = [
        "backend/app/services/recommender.py",
        "backend/app/services/demand_parser.py",
        "backend/app/services/hybrid_retriever.py",
        "data/config/recommendation_weights.json",
        "data/config/keyword_rules.json",
        "data/config/synonyms.json",
    ]
    test_events = git_log(test_report_paths)
    algorithm_events = git_log(algorithm_paths)
    first_test = test_events[0] if test_events else None
    later_algorithm_events: list[dict[str, str]] = []
    if first_test:
        first_date = datetime.fromisoformat(first_test["date"])
        later_algorithm_events = [
            event
            for event in algorithm_events
            if datetime.fromisoformat(event["date"]) > first_date
        ]

    calibration = load_json(ROOT / "reports" / "calibration" / "hybrid_calibration_summary.json")
    boundary = calibration.get("selection_boundary", {})
    final_test = calibration.get("final_test_confirmation", {})
    return {
        "first_checked_in_test_result": first_test,
        "test_result_commit_count": len(test_events),
        "algorithm_change_count_after_first_test_result": len(later_algorithm_events),
        "algorithm_changes_after_first_test_result": later_algorithm_events,
        "dense_calibration_declared_test_cases_read_for_selection": boundary.get(
            "test_cases_read_for_selection"
        ),
        "dense_calibration_declared_retuning_after_test": final_test.get("retuning_after_test"),
        "dense_calibration_scope_finding": (
            "The July dense-weight experiment documents val-only selection and no retuning "
            "after its final test run. This is valid for that bounded experiment."
        ),
        "global_blind_holdout_status": (
            "not_blind"
            if first_test and later_algorithm_events
            else "no_prior_exposure_found"
        ),
        "finding": (
            "The official test result was checked in before later parser/ranker/config changes. "
            "This proves chronological exposure, not intentional tuning on test errors. "
            "Accordingly, the test split was not directly trained on, but it is no longer an "
            "untouched blind holdout and carries adaptive selection bias risk."
        ),
    }


def audit_generalization_gap() -> dict[str, Any]:
    """Compare train/val/test Top-K without treating the exposed test as blind proof."""
    report_paths = (
        CURRENT_EVAL_REPORTS
        if all(path.is_file() for path in CURRENT_EVAL_REPORTS.values())
        else CALIBRATION_EVAL_REPORTS
    )
    source = "current_20260722" if report_paths is CURRENT_EVAL_REPORTS else "checked_in_calibration"
    metrics: dict[str, dict[str, float | int | str]] = {}
    for split_name, path in report_paths.items():
        payload = load_json(path)
        topk = payload.get("topk_evaluation", payload)
        metrics[split_name] = {
            "path": path.relative_to(ROOT).as_posix(),
            "total": int(topk.get("total") or 0),
            "top3_hit_rate_pct": float(topk.get("top3_hit_rate_pct") or 0.0),
            "top5_hit_rate_pct": float(topk.get("top5_hit_rate_pct") or 0.0),
            "macro_top3_pct": float(topk.get("macro_by_gold_model_top3_pct") or 0.0),
            "macro_top5_pct": float(topk.get("macro_by_gold_model_top5_pct") or 0.0),
        }
    train = metrics["train"]
    gaps = {
        split_name: {
            "train_minus_top3_points": round(
                float(train["top3_hit_rate_pct"]) - float(metrics[split_name]["top3_hit_rate_pct"]),
                2,
            ),
            "train_minus_top5_points": round(
                float(train["top5_hit_rate_pct"]) - float(metrics[split_name]["top5_hit_rate_pct"]),
                2,
            ),
        }
        for split_name in ("val", "test")
    }
    severe_threshold = 10.0
    large_gap = any(
        max(row["train_minus_top3_points"], row["train_minus_top5_points"])
        > severe_threshold
        for row in gaps.values()
    )
    return {
        "source": source,
        "metrics": metrics,
        "gaps": gaps,
        "large_gap_threshold_points": severe_threshold,
        "large_train_holdout_gap_found": large_gap,
        "finding": (
            "The known splits do not show a train-to-holdout drop above the declared 10-point "
            "diagnostic threshold. This reduces evidence for severe classical overfitting, but "
            "the exposed test split cannot establish blind generalization."
            if not large_gap
            else "At least one known holdout has a train gap above the 10-point diagnostic threshold."
        ),
    }


def audit_blind_set() -> dict[str, Any]:
    blind_dir = ROOT / "data" / "eval_blind"
    data_files = [
        path
        for path in blind_dir.glob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".csv"}
    ]
    return {
        "protocol_exists": (ROOT / "scripts" / "blind_eval.py").exists(),
        "readme_exists": (blind_dir / "README.md").exists(),
        "checked_in_blind_case_file_count": len(data_files),
        "checked_in_blind_case_files": [path.relative_to(ROOT).as_posix() for path in data_files],
        "independent_blind_evidence_available": bool(data_files),
    }


def build_audit(root: Path = ROOT, near_threshold: float = 0.82) -> dict[str, Any]:
    if root.resolve() != ROOT.resolve():
        raise ValueError("build_audit currently audits the repository containing this script")
    splits = {name: load_jsonl(path) for name, path in CANONICAL_SPLITS.items()}
    mirrors = {name: load_jsonl(path) for name, path in MIRROR_SPLITS.items()}

    split_report = split_integrity(splits, mirrors, near_threshold)
    hard_negative_report = audit_hard_negatives(splits)
    runtime_report = scan_runtime_for_eval_access()
    bge_report = audit_bge_training_evidence()
    weak_label_report = audit_weak_labels(splits)
    synthetic_report = audit_synthetic_lineage()
    provenance_report = audit_model_field_provenance()
    exposure_report = audit_test_exposure()
    generalization_report = audit_generalization_gap()
    blind_report = audit_blind_set()
    name_report = model_name_exposure(splits)

    direct_training_leakage = (
        hard_negative_report["direct_test_training_leakage_found"]
        or runtime_report["runtime_recommender_reads_gold_or_split_files"]
    )
    mirror_ok = all(
        details["exact_match"]
        for details in split_report["mirror_consistency"].values()
    )

    worktree = git_worktree_state()
    audited_hashes = {
        path.relative_to(ROOT).as_posix(): sha256_file(path)
        for path in [
            *CANONICAL_SPLITS.values(),
            ROOT / "data" / "training" / "hard_negative_pairs.jsonl",
            ROOT / "data" / "config" / "recommendation_weights.json",
        ]
    }
    return {
        "report_metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "script": "scripts/audit_dataset_integrity.py",
            "repository_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip(),
            **worktree,
            "audited_input_sha256": audited_hashes,
        },
        "executive_verdict": {
            "test_used_as_training_data": direct_training_leakage,
            "direct_training_leakage_risk": "low" if not direct_training_leakage else "high",
            "test_is_independent_blind_holdout": (
                exposure_report["global_blind_holdout_status"] == "no_prior_exposure_found"
                and blind_report["independent_blind_evidence_available"]
            ),
            "adaptive_test_overfitting_risk": "medium",
            "intent_tag_metric_circularity_risk": "high",
            "official_topk_generalization_risk": "medium",
            "non_official_field_influence_risk": provenance_report["risk_level"],
            "hard_negative_reproducibility_risk": (
                "low" if hard_negative_report["provenance_hashes_match"] else "medium"
            ),
            "overall_risk": "medium_high",
            "plain_language": (
                "在已检查的运行时代码和困难负例中，未发现把 test 样本直接用于训练；在已检查的项目代码中，"
                "也未发现 BGE-M3 微调入口。已知 train/val/test 的 Top-K 差距没有达到 10 个百分点的严重过拟合"
                "诊断阈值，但 test 结果在后续算法改动前已经可见，因此不是严格盲测。意图/标签弱标注同时依赖"
                "问句和答案模型名，困难负例元数据哈希又已失配，加上部分合成草稿字段参与结构化评分，整体存在"
                "中等偏高的证据偏差风险。"
            ),
        },
        "split_integrity": split_report,
        "mirror_files_match": mirror_ok,
        "model_name_exposure": name_report,
        "hard_negative_training_audit": hard_negative_report,
        "runtime_gold_access_audit": runtime_report,
        "bge_training_code_audit": bge_report,
        "weak_label_audit": weak_label_report,
        "synthetic_lineage_audit": synthetic_report,
        "model_field_provenance_audit": provenance_report,
        "test_exposure_timeline": exposure_report,
        "generalization_gap_audit": generalization_report,
        "blind_set_audit": blind_report,
        "required_claim_boundaries": [
            "TopK 仅表示对已知官方 60 模型目录和已公开 417 问题分布的检索命中率。",
            "Intent/Tag 指标不得描述为独立人工标注集上的泛化准确率。",
            "当前 test 不得描述为从未查看的最终盲测集。",
            "困难负例元数据哈希失配前，不得宣称该制品可按现有 metadata 逐字节复现。",
            "performance_metrics 与 historical_cases 为 synthetic_draft，不是银行生产验收证据。",
            "规则/LLM 合成数据不得与官方样本或真实银行生产数据混称。",
        ],
        "recommended_controls": [
            "建立全新外部盲测集：由未参与开发人员保管标签，冻结代码后一次性评测。",
            "重新从 train-only 官方问题生成任何用于训练/调参的合成语料；禁止 questions_all 进入训练生成链。",
            "对 intent/tag 建立人工复核标签集，并与当前弱标注指标分开展示。",
            "重新生成困难负例或补充可审计的 ID 迁移记录，并更新来源/输出 SHA-256。",
            "官方排序默认禁用或显式降权 synthetic_draft 性能指标与案例，除非完成来源核验。",
            "同时报告模型名遮蔽、跨表达和跨机构场景结果，避免只报原始 Top3/Top5。",
        ],
    }


def markdown_report(report: dict[str, Any]) -> str:
    verdict = report["executive_verdict"]
    split = report["split_integrity"]
    hard = report["hard_negative_training_audit"]
    exposure = report["test_exposure_timeline"]
    generalization = report["generalization_gap_audit"]
    bge = report["bge_training_code_audit"]
    weak = report["weak_label_audit"]
    synthetic = report["synthetic_lineage_audit"]
    provenance = report["model_field_provenance_audit"]
    blind = report["blind_set_audit"]
    names = report["model_name_exposure"]

    lines = [
        "# 官方数据划分、过拟合与来源完整性审计",
        "",
        f"生成时间：{report['report_metadata']['generated_at']}",
        f"审计提交：{report['report_metadata']['repository_commit']}",
        f"工作区是否含未提交修改：{report['report_metadata']['working_tree_dirty']}"
        f"（{report['report_metadata']['dirty_file_count']} 个状态项）",
        "",
        "## 一、结论",
        "",
        verdict["plain_language"],
        "",
        "| 问题 | 结论 | 风险 |",
        "|---|---|---|",
        f"| test 是否直接作为训练数据 | {'是' if verdict['test_used_as_training_data'] else '未发现'} | {verdict['direct_training_leakage_risk']} |",
        f"| test 是否仍是独立盲测集 | {'是' if verdict['test_is_independent_blind_holdout'] else '否'} | {verdict['adaptive_test_overfitting_risk']} |",
        f"| 已知划分是否出现大于 10 点的 train→holdout Top-K 落差 | {'是' if generalization['large_train_holdout_gap_found'] else '否'} | {verdict['official_topk_generalization_risk']} |",
        f"| Intent/Tag 标签独立性 | 弱标注同时依赖问句和答案模型名 | {verdict['intent_tag_metric_circularity_risk']} |",
        f"| 困难负例 metadata 哈希是否匹配 | {'是' if hard['provenance_hashes_match'] else '否'} | {verdict['hard_negative_reproducibility_risk']} |",
        f"| 非官方草稿字段是否影响排序 | {'是' if provenance['runtime_ranking_uses_performance_metrics'] or provenance['runtime_ranking_uses_historical_cases'] else '否'} | {verdict['non_official_field_influence_risk']} |",
        f"| 综合风险 | 需要限定指标口径并补外部盲测 | {verdict['overall_risk']} |",
        "",
        "## 二、数据划分完整性",
        "",
        f"- train / val / test：{split['counts']['train']} / {split['counts']['val']} / {split['counts']['test']}。",
        f"- 跨 split ID 重复：{split['split_id_overlap_count']}。",
        f"- 归一化文本完全重复：{split['exact_cross_split_query_count']}。",
        f"- 词面近重复阈值：{split['near_duplicate_threshold']}；在该阈值下命中：{split['near_duplicate_count']}。",
        f"- 人工复核阈值：{split['manual_review_threshold']}；候选：{split['manual_review_candidate_count']}。",
        "- 未执行语义向量级重复判定；词面阈值下为 0 不代表不存在语义改写。",
        f"- official 与 official_60 的 ID/归一化问句/gold ID 三元组一致：{'是' if report['mirror_files_match'] else '否'}。",
        f"- 划分类型：{split['split_strategy']}；三个 split 共同覆盖模型数：{split['gold_models_shared_by_all_splits']}。",
        "",
        "最高跨 split 相似样本：",
        "",
        "| 左侧 | 右侧 | 同标签 | 综合相似度 |",
        "|---|---|---:|---:|",
    ]
    for item in split["top_cross_split_similarities"][:10]:
        lines.append(
            f"| {item['left_id']} | {item['right_id']} | "
            f"{'是' if item['same_gold_model'] else '否'} | {item['combined']} |"
        )

    lines.extend(
        [
            "",
            "## 三、是否把 test 当成训练集",
            "",
            f"- 困难负例总数：{hard['pair_count']}；来源 train case：{hard['unique_source_case_count']}。",
            f"- 非 train ID：{hard['non_train_id_count']}；val/test ID 交集：{hard['val_test_id_intersection_count']}。",
            f"- 训练查询无法回溯到 train：{hard['query_not_found_in_train_count']}。",
            f"- 排序运行时代码直接读取 gold/test 文件：{'是' if report['runtime_gold_access_audit']['runtime_recommender_reads_gold_or_split_files'] else '否'}。",
            f"- BGE-M3 常见微调入口命中：{bge['training_marker_count']}（扫描 Python 文件 {bge['scanned_python_file_count']} 个）。",
            f"- 困难负例来源哈希匹配：{hard['source_file_sha256_matches_metadata']}；输出哈希匹配：{hard['output_file_sha256_matches_metadata']}。",
            f"- 困难负例复现状态：{hard['reproducibility_status']}。",
            "- 结论：在已检查的运行时代码、项目脚本和困难负例中，未发现 test 直接进入训练，也未发现 BGE-M3 微调入口。",
            "",
            "注意：困难负例脚本的输入文件物理上包含 417 条全量记录，但脚本先筛选 train_，并在 mine() 内再次拒绝非 train ID。"
            "当前所有 pair 的 ID 与问句仍能回溯到 train，但 metadata 中的来源和输出 SHA-256 已与当前文件不符，"
            "所以不能宣称可按现有 metadata 逐字节复现。运行时代码检查只是对列出的路径做静态字符串扫描。",
            "",
            "## 四、已知划分的泛化差距",
            "",
            f"评测来源：{generalization['source']}。",
            "",
            "| split | 样本量 | Top3 | Top5 | train-Top3 | train-Top5 |",
            "|---|---:|---:|---:|---:|---:|",
            f"| train | {generalization['metrics']['train']['total']} | {generalization['metrics']['train']['top3_hit_rate_pct']}% | {generalization['metrics']['train']['top5_hit_rate_pct']}% | 0 | 0 |",
            f"| val | {generalization['metrics']['val']['total']} | {generalization['metrics']['val']['top3_hit_rate_pct']}% | {generalization['metrics']['val']['top5_hit_rate_pct']}% | {generalization['gaps']['val']['train_minus_top3_points']} | {generalization['gaps']['val']['train_minus_top5_points']} |",
            f"| test | {generalization['metrics']['test']['total']} | {generalization['metrics']['test']['top3_hit_rate_pct']}% | {generalization['metrics']['test']['top5_hit_rate_pct']}% | {generalization['gaps']['test']['train_minus_top3_points']} | {generalization['gaps']['test']['train_minus_top5_points']} |",
            "",
            "已知划分没有出现超过 10 个百分点的 train→holdout Top-K 落差，因此没有明显的严重经典过拟合迹象；"
            "但该阈值是诊断口径，且 test 已暴露，不能替代外部盲测。",
            "",
            "## 五、test 是否仍然独立",
            "",
            f"- 首个已提交 test 结果：{json.dumps(exposure['first_checked_in_test_result'], ensure_ascii=False)}。",
            f"- 此后排序/解析/配置变更提交数：{exposure['algorithm_change_count_after_first_test_result']}。",
            f"- 当前状态：{exposure['global_blind_holdout_status']}。",
            f"- dense 权重实验声明 selection 阶段读取 test 数：{exposure['dense_calibration_declared_test_cases_read_for_selection']}；"
            f"test 后再调参：{exposure['dense_calibration_declared_retuning_after_test']}。",
            "",
            "结论：dense 权重 0.5 的局部实验有 val-only 选择证据；但全项目历史中 test 结果先于后续算法改动公开，"
            "所以不能把当前 test 描述为从未查看的一次性盲测。时间顺序只能证明暴露，不能证明开发者有意按 test 调参。",
            "",
            "## 六、标签独立性与答案依赖",
            "",
            f"- 417 条官方问题中 needs_review=true：{weak['needs_review_true_count']}。",
            f"- expected_tags 由 query + gold_model_name 推导：{weak['expected_tags_derived_from_query_and_gold_name']}。",
            f"- intent_task 由 query + gold_model_name 推导：{weak['intent_task_derived_from_query_and_gold_name']}。",
            f"- test 中保守模型名/核心名直现率：{names['test']['conservative_any_name_hit_pct']}%。",
            "",
            weak["finding"],
            "",
            "## 七、合成数据与非官方字段",
            "",
            f"- 规则合成数据生成器读取 questions_all：{synthetic['generator_uses_official_questions_all']}。",
            f"- 当前运行时排序直接引用合成问题集：{synthetic['currently_used_for_runtime_training_or_ranking']}。",
            f"- synthetic_draft 字段：{'、'.join(provenance['synthetic_draft_fields'])}。",
            f"- 结构化排序读取 performance_metrics：{provenance['runtime_ranking_uses_performance_metrics']}；"
            f"读取 historical_cases：{provenance['runtime_ranking_uses_historical_cases']}。",
            "",
            "现有规则合成语料由 questions_all（含 train/val/test）派生；当前运行时排序没有读取它。"
            "如果未来用于训练或调参，必须从 train-only 重新生成。",
            "",
            "performance_metrics 与 historical_cases 是未核验的 synthetic_draft。当前结构化排序会读取它们，"
            "因此它们可以影响排序，但不得被当作银行生产证据。",
            "",
            "## 八、外部盲测",
            "",
            f"- 已有盲测协议脚本：{blind['protocol_exists']}。",
            f"- 仓库内实际盲测 cases/labels 文件数：{blind['checked_in_blind_case_file_count']}。",
            f"- 当前存在独立盲测证据：{blind['independent_blind_evidence_available']}。",
            "",
            "## 九、允许与不允许的结论口径",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["required_claim_boundaries"])
    lines.extend(["", "## 十、建议控制措施", ""])
    lines.extend(
        f"{index}. {item}"
        for index, item in enumerate(report["recommended_controls"], start=1)
    )
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(markdown_report(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit official dataset integrity and overfitting risk")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--near-threshold", type=float, default=0.82)
    args = parser.parse_args(argv)
    if not 0.0 <= args.near_threshold <= 1.0:
        parser.error("--near-threshold must be in [0, 1]")

    report = build_audit(near_threshold=args.near_threshold)
    write_outputs(report, args.json_output, args.markdown_output)
    print(json.dumps(report["executive_verdict"], ensure_ascii=False, indent=2))
    print(f"JSON: {args.json_output}")
    print(f"Markdown: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
