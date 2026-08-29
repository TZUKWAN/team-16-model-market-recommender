import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from asset_catalog_versions import AssetCatalogVersionStore  # noqa: E402
from app.repositories.model_asset_repository import ModelAssetRepository


def valid_row(model_id: str) -> dict:
    return {
        "model_id": model_id,
        "model_name": f"Model {model_id}",
        "domain": "credit_risk",
        "business_scenario": ["pre-loan admission"],
        "business_stage": ["pre_loan"],
        "customer_segment": ["small_micro_enterprise"],
        "model_capability": ["admission_scoring"],
        "input_fields_required": ["customer_profile"],
        "output_fields": ["risk_score"],
        "tags": ["credit_risk", "pre_loan", "small_micro_enterprise", "admission_scoring"],
        "description": "test model",
        "input_schema": {"type": "object", "properties": {"a": {"type": "string"}}},
        "output_schema": {"type": "object"},
        "result_schema": {"type": "object"},
    }


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_official_and_demo_catalog_counts(tmp_path):
    official_store = AssetCatalogVersionStore(tmp_path / "official_catalog")
    official = official_store.import_path(
        ROOT / "data" / "official" / "model_catalog_structured.jsonl", "official", "official-v1"
    )
    demo_store = AssetCatalogVersionStore(tmp_path / "demo_catalog")
    demo = demo_store.import_path(ROOT / "data" / "knowledge", "demo", "demo-v1")
    assert official["accepted_count"] == 60
    assert official["quarantine_count"] == 0
    assert demo["accepted_count"] == 105
    assert demo["quarantine_count"] == 0


def test_quarantine_schema_change_soft_delete_and_rollback(tmp_path, monkeypatch):
    catalog = tmp_path / "catalog"
    store = AssetCatalogVersionStore(catalog)
    first_path = tmp_path / "first.jsonl"
    write_rows(first_path, [valid_row("A"), valid_row("B")])
    first = store.import_path(first_path, "imported", "v1")
    assert first["accepted_count"] == 2

    changed = valid_row("A")
    changed["input_schema"] = {"type": "object", "properties": {"changed": {"type": "number"}}}
    bad = valid_row("BAD")
    bad["input_fields_required"] = ["not_a_real_field"]
    second_path = tmp_path / "second.jsonl"
    write_rows(second_path, [changed, changed, bad])
    second = store.import_path(second_path, "imported", "v2")
    assert second["accepted_count"] == 1
    assert second["quarantine_count"] == 2
    assert second["soft_deleted_model_ids"] == ["B"]
    assert {item["field"] for item in second["schema_changes"]} == {"input_schema"}
    assert store.active_version() == "v2"
    assert store.rollback() == "v1"

    monkeypatch.setenv("MODEL_ASSET_CATALOG_DIR", str(catalog))
    monkeypatch.setenv("MODEL_ASSET_VERSION", "v1")
    repository = ModelAssetRepository()
    assert repository.stats().total_models == 2
    assert repository.get_model("A") is not None


def test_duplicate_version_and_missing_configured_version_fail(tmp_path, monkeypatch):
    store = AssetCatalogVersionStore(tmp_path / "catalog")
    path = tmp_path / "models.jsonl"
    write_rows(path, [valid_row("A")])
    store.import_path(path, "imported", "v1")
    with pytest.raises(ValueError, match="already exists"):
        store.import_path(path, "imported", "v1")
    monkeypatch.setenv("MODEL_ASSET_CATALOG_DIR", str(tmp_path / "catalog"))
    monkeypatch.setenv("MODEL_ASSET_VERSION", "missing")
    with pytest.raises(FileNotFoundError):
        ModelAssetRepository()
