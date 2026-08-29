"""Tests for scripts/import_model_assets.py."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import import_model_assets as importer  # noqa: E402


def valid_row(model_id: str = "TEST_001") -> dict:
    return {
        "model_id": model_id,
        "model_name": "测试准入模型",
        "domain": "credit_risk",
        "business_scenario": "测试贷前准入",
        "business_stage": "pre_loan",
        "customer_segment": "small_micro_enterprise",
        "model_capability": "admission_scoring",
        "input_fields_required": "customer_profile|credit_report",
        "input_fields_optional": "business_operation",
        "output_fields": "risk_score|admission_decision",
        "performance_metrics": '{"auc":0.82}',
        "api_available": "true",
        "tags": "credit_risk|pre_loan|small_micro_enterprise|admission_scoring",
        "description": "用于测试的小微企业贷前准入模型。",
    }


def test_import_jsonl_success(tmp_path):
    input_path = tmp_path / "models.jsonl"
    output_path = tmp_path / "out.jsonl"
    input_path.write_text(json.dumps(valid_row(), ensure_ascii=False) + "\n", encoding="utf-8")

    code = importer.main([
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--source",
        "imported",
    ])

    assert code == 0
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["model_id"] == "TEST_001"
    assert rows[0]["input_fields_required"] == ["customer_profile", "credit_report"]
    assert rows[0]["api_available"] is True


def test_import_csv_success(tmp_path):
    input_path = tmp_path / "models.csv"
    output_path = tmp_path / "out.jsonl"
    row = valid_row("TEST_CSV_001")
    headers = list(row.keys())
    input_path.write_text(
        ",".join(headers) + "\n" + ",".join(str(row[h]) for h in headers) + "\n",
        encoding="utf-8",
    )

    code = importer.main(["--input", str(input_path), "--output", str(output_path)])

    assert code == 0
    assert "TEST_CSV_001" in output_path.read_text(encoding="utf-8")


def test_import_xlsx_success(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    input_path = tmp_path / "models.xlsx"
    output_path = tmp_path / "out.jsonl"
    row = valid_row("TEST_XLSX_001")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(row.keys()))
    ws.append([row[k] for k in row.keys()])
    wb.save(input_path)

    code = importer.main(["--input", str(input_path), "--output", str(output_path)])

    assert code == 0
    assert "TEST_XLSX_001" in output_path.read_text(encoding="utf-8")


def test_import_bad_data_returns_nonzero(tmp_path):
    input_path = tmp_path / "bad.jsonl"
    output_path = tmp_path / "out.jsonl"
    bad = valid_row("BAD_001")
    bad["input_fields_required"] = "not_a_real_field"
    input_path.write_text(json.dumps(bad, ensure_ascii=False) + "\n", encoding="utf-8")

    code = importer.main(["--input", str(input_path), "--output", str(output_path)])

    assert code == 1
    assert not output_path.exists()


def test_import_rejects_oversized_input(tmp_path):
    input_path = tmp_path / "too-large.json"
    input_path.write_bytes(b" " * (importer.MAX_IMPORT_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="exceeds"):
        importer.read_records(input_path)


def test_import_rejects_excessive_json_depth(tmp_path):
    value = "leaf"
    for _ in range(importer.MAX_IMPORT_JSON_DEPTH + 2):
        value = {"nested": value}
    input_path = tmp_path / "deep.json"
    input_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="nesting"):
        importer.read_records(input_path)


def test_official_sparse_catalog_dry_run():
    input_path = Path(__file__).resolve().parents[2] / "data" / "official" / "model_catalog_structured.jsonl"

    code = importer.main([
        "--input",
        str(input_path),
        "--output",
        str(Path("reports/imports/test_official.jsonl")),
        "--source",
        "official",
        "--dry-run",
    ])

    assert code == 0
