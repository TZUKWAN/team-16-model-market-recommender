"""Tests for ModelAssetRepository."""

from app.repositories.model_asset_repository import ModelAssetRepository


def test_repository_loads_demo_and_official_assets():
    """Repository should expose the combined normalized model catalog."""
    repo = ModelAssetRepository()
    stats = repo.stats()

    assert stats.total_models >= 165
    assert stats.by_source.get("demo", 0) >= 105
    assert stats.by_source.get("official", 0) >= 60
    assert repo.get_model("MKT_001") is not None
    assert repo.get_model("OFFICIAL_001") is not None


def test_repository_normalizes_asset_fields():
    """Repository should add required operational metadata and schemas."""
    repo = ModelAssetRepository()
    model = repo.get_model("MKT_001")

    assert model is not None
    assert model["asset_version"]
    assert model["asset_status"]
    assert model["permission_scope"] == "demo_desensitized"
    assert model["input_schema"]["type"] == "object"
    assert model["output_schema"]["type"] == "object"
    assert model["result_schema"]["type"] == "object"
    official = repo.get_model("OFFICIAL_001")
    assert official is not None
    assert official["field_provenance"]["canonical_name"]["verification"] == "source_verified"
    assert official["field_provenance"]["performance_metrics"]["source_type"] == "synthetic_draft"
    assert official["field_provenance"]["performance_metrics"]["verification"] == "unverified_do_not_use_as_production_fact"


def test_repository_filters_by_source_and_domain():
    """Repository should support source/domain filtering for downstream services."""
    repo = ModelAssetRepository()

    official_models = repo.list_models(source="official")
    marketing_models = repo.list_models(domain="customer_marketing")

    assert official_models
    assert all(m["source"] == "official" for m in official_models)
    assert marketing_models
    assert all(m["domain"] == "customer_marketing" for m in marketing_models)


def test_repository_reports_duplicate_and_missing_fields():
    """Repository validation should catch duplicate ids and missing required fields."""
    raw_models = [
        {
            "model_id": "DUP_001",
            "model_name": "测试模型",
            "domain": "customer_marketing",
            "business_scenario": ["测试"],
            "business_stage": ["marketing"],
            "model_capability": ["ranking"],
            "input_fields_required": ["customer_profile"],
            "output_fields": ["score"],
            "description": "测试描述",
        },
        {
            "model_id": "DUP_001",
            "model_name": "重复模型",
            "domain": "customer_marketing",
        },
        {
            "model_id": "BAD_001",
            "model_name": "",
            "domain": "",
        },
    ]

    repo = ModelAssetRepository(raw_models=raw_models)
    issues = repo.validation_issues()

    assert repo.stats().total_models == 2
    assert any(issue.field == "model_id" and "duplicate" in issue.message for issue in issues)
    assert any(issue.model_id == "BAD_001" and issue.field == "model_name" for issue in issues)
