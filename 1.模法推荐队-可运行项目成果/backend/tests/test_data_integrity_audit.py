"""Regression checks for the reproducible data-integrity audit."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_dataset_integrity.py"
SPEC = importlib.util.spec_from_file_location("audit_dataset_integrity", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_normalize_text_removes_formatting_without_changing_meaning():
    assert module.normalize_text(" AUM 10-30万？ ") == "aum1030万"


def test_current_repository_has_no_direct_test_training_leakage():
    report = module.build_audit()

    assert report["split_integrity"]["counts"] == {"train": 291, "val": 64, "test": 62}
    assert report["split_integrity"]["split_id_overlap_count"] == 0
    assert report["mirror_files_match"] is True
    assert report["hard_negative_training_audit"]["non_train_id_count"] == 0
    assert report["hard_negative_training_audit"]["val_test_id_intersection_count"] == 0
    assert report["runtime_gold_access_audit"]["runtime_recommender_reads_gold_or_split_files"] is False
    assert report["bge_training_code_audit"]["project_finetuning_evidence_found"] is False
    assert report["executive_verdict"]["test_used_as_training_data"] is False


def test_audit_does_not_mislabel_the_exposed_test_as_blind():
    report = module.build_audit()

    assert report["test_exposure_timeline"]["global_blind_holdout_status"] == "not_blind"
    assert report["test_exposure_timeline"]["algorithm_change_count_after_first_test_result"] > 0
    assert report["executive_verdict"]["test_is_independent_blind_holdout"] is False
    assert report["weak_label_audit"]["risk_by_metric"]["intent_accuracy"] == "high"
    assert report["weak_label_audit"]["expected_tags_derived_from_query_and_gold_name"] is True
    assert report["generalization_gap_audit"]["large_train_holdout_gap_found"] is False
    assert report["split_integrity"]["semantic_duplicate_check_performed"] is False


def test_canary_injected_test_pair_is_detected_as_leakage():
    """Inject a fake hard-negative pair with a test ID and verify the audit flags it."""
    import hashlib
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        train_dir = tmp_root / "data" / "training"
        eval_dir = tmp_root / "data" / "eval_official"
        train_dir.mkdir(parents=True)
        eval_dir.mkdir(parents=True)

        fake_pair = {
            "pair_id": "test_0001_hn1",
            "source_test_id": "test_0001",
            "source_split": "test",
            "query": "canary injected query",
            "positive_model_id": "OFFICIAL_001",
            "negative_model_id": "OFFICIAL_002",
        }
        pairs_path = train_dir / "hard_negative_pairs.jsonl"
        pairs_path.write_text(json.dumps(fake_pair, ensure_ascii=False) + "\n", encoding="utf-8")

        source_path = eval_dir / "topk_eval_official.jsonl"
        source_path.write_text("{}\n", encoding="utf-8")

        def sha256_file(path: Path) -> str:
            digest = hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        metadata = {
            "source_split": "test",
            "source_case_count": 1,
            "source_file_sha256": sha256_file(source_path),
            "output_file_sha256": sha256_file(pairs_path),
        }
        (train_dir / "hard_negative_pairs.metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
        )

        splits = {
            "train": [
                {
                    "question_id": "train_0001",
                    "user_query": "train query",
                    "gold_model_id": "OFFICIAL_001",
                }
            ],
            "val": [],
            "test": [
                {
                    "question_id": "test_0001",
                    "user_query": "canary injected query",
                    "gold_model_id": "OFFICIAL_001",
                }
            ],
        }

        original_root = module.ROOT
        module.ROOT = tmp_root
        try:
            report = module.audit_hard_negatives(splits)
            assert report["direct_test_training_leakage_found"] is True
            assert report["non_train_id_count"] > 0
            assert report["val_test_id_intersection_count"] > 0
        finally:
            module.ROOT = original_root


def test_hard_negative_pairs_are_valid_and_unique():
    """Verify hard-negative positives match train gold, negatives differ, pair IDs are unique."""
    report = module.build_audit()
    hard = report["hard_negative_training_audit"]
    assert hard["direct_test_training_leakage_found"] is False
    assert hard["non_train_id_count"] == 0
    assert hard["val_test_id_intersection_count"] == 0

    pairs = module.load_jsonl(
        module.ROOT / "data" / "training" / "hard_negative_pairs.jsonl"
    )
    train_rows = module.load_jsonl(
        module.ROOT / "data" / "official" / "questions_train.jsonl"
    )
    train_by_id = {module.row_id(row): row for row in train_rows}
    catalog = module.load_jsonl(
        module.ROOT / "data" / "official" / "model_catalog_structured.jsonl"
    )
    valid_model_ids = {row["model_id"] for row in catalog}

    pair_ids: set[str] = set()
    for pair in pairs:
        pair_id = str(pair.get("pair_id") or "")
        assert pair_id not in pair_ids, f"duplicate pair_id: {pair_id}"
        pair_ids.add(pair_id)

        source_id = str(pair.get("source_test_id") or "")
        assert source_id in train_by_id, f"source_test_id {source_id} not in train"

        train_row = train_by_id[source_id]
        assert module.normalize_text(pair.get("query", "")) == module.normalize_text(
            module.row_query(train_row)
        ), f"query mismatch for {source_id}"
        assert pair.get("positive_model_id") == module.row_gold_id(
            train_row
        ), f"positive_model_id mismatch for {source_id}"

        negative_model_id = pair.get("negative_model_id")
        assert negative_model_id in valid_model_ids, f"negative_model_id {negative_model_id} not in catalog"
        assert negative_model_id != pair.get("positive_model_id"), f"negative equals positive in {pair_id}"
