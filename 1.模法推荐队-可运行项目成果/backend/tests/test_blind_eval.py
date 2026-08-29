"""Tests for the independent blind-evaluation evidence gate."""

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "blind_eval.py"
    spec = importlib.util.spec_from_file_location("blind_eval", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def valid_rows():
    cases = [
        {
            "case_id": "blind_0001",
            "query": "我们希望识别未来可能减少活期存款的高价值客户，应重点考虑哪类能力？",
            "scenario": "customer_marketing",
            "author_id": "author-a",
            "authorship_attestation": "independent_human_authored",
        }
    ]
    labels = [
        {
            "case_id": "blind_0001",
            "primary_model_id": "OFFICIAL_060",
            "acceptable_model_ids": ["OFFICIAL_060"],
            "reviewer_id": "reviewer-b",
            "review_status": "approved",
            "review_attestation": "independent_human_review",
        }
    ]
    return cases, labels


def test_valid_independent_rows_pass_with_small_set_warning():
    module = load_script()
    cases, labels = valid_rows()
    result = module.validate_blind_dataset(
        cases,
        labels,
        official_queries=["一个完全不同的官方测试问题"],
        model_names={"OFFICIAL_060": "高价值存款客户流失预测模型"},
    )

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["warnings"]


@pytest.mark.parametrize("defect", ["gold_leak", "same_reviewer", "official_duplicate", "model_name"])
def test_formal_gate_rejects_invalid_evidence(defect):
    module = load_script()
    cases, labels = valid_rows()
    official = ["一个完全不同的官方测试问题"]
    if defect == "gold_leak":
        cases[0]["gold_model_id"] = "OFFICIAL_060"
    elif defect == "same_reviewer":
        labels[0]["reviewer_id"] = "author-a"
    elif defect == "official_duplicate":
        official = [cases[0]["query"]]
    else:
        cases[0]["query"] = "请推荐高价值存款客户流失预测模型"

    result = module.validate_blind_dataset(
        cases,
        labels,
        official_queries=official,
        model_names={"OFFICIAL_060": "高价值存款客户流失预测模型"},
    )

    assert result["valid"] is False
    assert result["errors"]


def test_manifest_detects_post_freeze_tampering(tmp_path):
    module = load_script()
    cases, labels = valid_rows()
    cases_path = tmp_path / "cases.jsonl"
    labels_path = tmp_path / "labels.private.jsonl"
    manifest_path = tmp_path / "manifest.json"
    cases_path.write_text(json.dumps(cases[0], ensure_ascii=False) + "\n", encoding="utf-8")
    labels_path.write_text(json.dumps(labels[0], ensure_ascii=False) + "\n", encoding="utf-8")
    validation = module.validate_blind_dataset(
        cases,
        labels,
        official_queries=["一个完全不同的官方测试问题"],
        model_names={"OFFICIAL_060": "高价值存款客户流失预测模型"},
    )
    module.create_manifest(cases_path, labels_path, manifest_path, validation)
    module.verify_manifest(cases_path, labels_path, manifest_path)

    cases_path.write_text(cases_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after freeze"):
        module.verify_manifest(cases_path, labels_path, manifest_path)


def test_software_gate_never_self_declares_formal_human_evidence(tmp_path):
    module = load_script()
    paths = []
    for name in ("manifest.json", "cases.jsonl", "labels.private.jsonl"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        paths.append(path)

    report = module.build_blind_report(
        manifest_path=paths[0],
        cases_path=paths[1],
        labels_path=paths[2],
        validation={"valid": True},
        evaluation={"total": 1},
    )

    assert report["blind_software_gate_passed"] is True
    assert report["formal_blind_evidence"] is False
    assert "external_human_identity" in report["formal_evidence_status"]
