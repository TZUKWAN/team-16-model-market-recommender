"""Repository for model assets from demo, official, and future imported catalogs.

The repository gives recommendation, model-detail, composition, and future graph
services one normalized asset boundary instead of each module reading raw JSON
files independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import copy
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.services.data_loader import load_models

logger = logging.getLogger(__name__)


REQUIRED_MODEL_FIELDS = (
    "model_id",
    "model_name",
    "domain",
    "business_scenario",
    "business_stage",
    "model_capability",
    "input_fields_required",
    "output_fields",
    "description",
)


@dataclass(frozen=True)
class AssetValidationIssue:
    """Validation issue for a model asset."""

    model_id: str
    field: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class AssetRepositoryStats:
    """Repository inventory summary."""

    total_models: int
    by_source: dict[str, int] = field(default_factory=dict)
    by_domain: dict[str, int] = field(default_factory=dict)
    api_available: int = 0


class ModelAssetRepository:
    """Normalized read repository for model assets."""

    def __init__(self, raw_models: list[dict[str, Any]] | None = None):
        self._raw_models = raw_models
        self._models_by_id: dict[str, dict[str, Any]] = {}
        self._issues: list[AssetValidationIssue] = []
        self.reload()

    def reload(self) -> None:
        """Reload and normalize assets from the configured source."""
        raw_models = self._raw_models if self._raw_models is not None else self._load_configured_models()
        models_by_id: dict[str, dict[str, Any]] = {}
        issues: list[AssetValidationIssue] = []

        for index, raw in enumerate(raw_models):
            model = self._normalize_model(raw)
            model_id = model.get("model_id") or f"__missing_id_{index}"
            if not model.get("model_id"):
                issues.append(AssetValidationIssue(model_id, "model_id", "model_id is required"))
                continue
            if model_id in models_by_id:
                issues.append(AssetValidationIssue(model_id, "model_id", "duplicate model_id"))
                continue

            issues.extend(self._validate_model(model))
            models_by_id[model_id] = model

        self._models_by_id = models_by_id
        self._issues = issues

    @staticmethod
    def _load_configured_models() -> list[dict[str, Any]]:
        version = os.getenv("MODEL_ASSET_VERSION", "").strip()
        if not version:
            return load_models()
        root = Path(__file__).resolve().parents[3]
        catalog_dir = Path(os.getenv("MODEL_ASSET_CATALOG_DIR", "data/model_catalog"))
        if not catalog_dir.is_absolute():
            catalog_dir = root / catalog_dir
        path = catalog_dir / "versions" / version / "models.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"Configured model asset version does not exist: {version}")
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        logger.info(
            "Loaded %s normalized model assets with %s validation issues",
            len(self._models_by_id),
            len(self._issues),
        )

    def list_models(self, source: str | None = None, domain: str | None = None) -> list[dict[str, Any]]:
        """Return normalized model assets, optionally filtered by source/domain."""
        models = list(self._models_by_id.values())
        if source:
            models = [m for m in models if m.get("source") == source]
        if domain:
            models = [m for m in models if m.get("domain") == domain]
        return [copy.deepcopy(m) for m in models]

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        """Return one normalized model asset by id."""
        model = self._models_by_id.get(model_id)
        return copy.deepcopy(model) if model else None

    def model_ids(self) -> set[str]:
        """Return all known model IDs."""
        return set(self._models_by_id)

    def validation_issues(self) -> list[AssetValidationIssue]:
        """Return validation issues found during loading."""
        return list(self._issues)

    def stats(self) -> AssetRepositoryStats:
        """Return inventory counts for health checks and audits."""
        by_source: dict[str, int] = {}
        by_domain: dict[str, int] = {}
        api_available = 0
        for model in self._models_by_id.values():
            source = str(model.get("source") or "unknown")
            domain = str(model.get("domain") or "unknown")
            by_source[source] = by_source.get(source, 0) + 1
            by_domain[domain] = by_domain.get(domain, 0) + 1
            if model.get("api_available"):
                api_available += 1
        return AssetRepositoryStats(
            total_models=len(self._models_by_id),
            by_source=by_source,
            by_domain=by_domain,
            api_available=api_available,
        )

    def _normalize_model(self, raw: dict[str, Any]) -> dict[str, Any]:
        model = dict(raw or {})
        source = str(model.get("source") or "demo")
        model["source"] = source
        model["asset_version"] = str(model.get("asset_version") or model.get("version") or "1.0.0")
        model["asset_status"] = str(
            model.get("asset_status") or model.get("deployment_status") or "cataloged"
        )
        model["permission_scope"] = str(model.get("permission_scope") or self._default_permission_scope(source))
        model["legal_boundary"] = str(
            model.get("legal_boundary") or model.get("compliance_boundary") or ""
        )
        model["business_scenario"] = self._list(model.get("business_scenario"))
        model["business_stage"] = self._list(model.get("business_stage"))
        if not model["business_stage"]:
            model["business_stage"] = self._default_business_stage(str(model.get("domain", "")))
        model["customer_segment"] = self._list(model.get("customer_segment"))
        model["model_capability"] = self._list(model.get("model_capability"))
        model["input_fields_required"] = self._list(model.get("input_fields_required"))
        model["input_fields_optional"] = self._list(model.get("input_fields_optional"))
        model["output_fields"] = self._list(model.get("output_fields"))
        model["historical_cases"] = self._normalize_historical_cases(model.get("historical_cases"))
        model["tags"] = self._list(model.get("tags"))
        model["aliases"] = self._list(model.get("aliases"))
        model["api_available"] = bool(model.get("api_available", False))
        model["input_schema"] = model.get("input_schema") or self._schema_from_fields(
            model["input_fields_required"],
            required=True,
        )
        model["output_schema"] = model.get("output_schema") or self._schema_from_fields(
            model["output_fields"],
            required=False,
        )
        model["result_schema"] = model.get("result_schema") or {
            "type": "object",
            "properties": model["output_schema"].get("properties", {}),
        }
        model["field_provenance"] = model.get("field_provenance") or self._field_provenance(
            model, source
        )
        return model

    @staticmethod
    def _field_provenance(model: dict[str, Any], source: str) -> dict[str, dict[str, str]]:
        if source != "official":
            return {
                field: {
                    "source_type": "demo_or_imported",
                    "provenance": source,
                    "verification": "demo_only" if source == "demo" else "unverified",
                }
                for field in model
                if field != "field_provenance"
            }
        raw_fields = {"canonical_name", "description", "total_questions"}
        draft_fields = {"performance_metrics", "historical_cases"}
        provenance: dict[str, dict[str, str]] = {}
        for field in model:
            if field == "field_provenance":
                continue
            if field in raw_fields:
                provenance[field] = {
                    "source_type": "official_raw",
                    "provenance": "competition_official_catalog",
                    "verification": "source_verified",
                }
            elif field in draft_fields:
                provenance[field] = {
                    "source_type": "synthetic_draft",
                    "provenance": "deterministic_local_rules_no_external_evidence",
                    "verification": "unverified_do_not_use_as_production_fact",
                }
            else:
                provenance[field] = {
                    "source_type": "deterministic_inference",
                    "provenance": "derived_from_official_description_or_local_taxonomy",
                    "verification": "draft_requires_manual_review",
                }
        return provenance

    def _validate_model(self, model: dict[str, Any]) -> list[AssetValidationIssue]:
        issues: list[AssetValidationIssue] = []
        model_id = str(model.get("model_id", ""))
        for field_name in REQUIRED_MODEL_FIELDS:
            value = model.get(field_name)
            if value in ("", None, [], {}):
                issues.append(AssetValidationIssue(model_id, field_name, f"{field_name} is required"))
        return issues

    @staticmethod
    def _list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, tuple | set):
            return [str(v).strip() for v in value if str(v).strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _normalize_historical_cases(value: Any) -> list[str]:
        cases: list[str] = []
        for item in ModelAssetRepository._list(value):
            cases.append(item)
        if isinstance(value, list):
            cases = []
            for item in value:
                if isinstance(item, dict):
                    client = str(item.get("client", "")).strip()
                    result = str(
                        item.get("result") or item.get("effect") or item.get("description") or ""
                    ).strip()
                    text = f"{client}: {result}".strip(": ")
                    if text:
                        cases.append(text)
                else:
                    text = str(item).strip()
                    if text:
                        cases.append(text)
        return cases

    @staticmethod
    def _schema_from_fields(fields: list[str], required: bool) -> dict[str, Any]:
        return {
            "type": "object",
            "required": fields if required else [],
            "properties": {
                field: {"type": "number|string|array|object", "description": field}
                for field in fields
            },
        }

    @staticmethod
    def _default_permission_scope(source: str) -> str:
        if source == "official":
            return "official_catalog_internal"
        return "demo_desensitized"

    @staticmethod
    def _default_business_stage(domain: str) -> list[str]:
        if domain == "credit_risk":
            return ["risk_management"]
        if domain == "customer_marketing":
            return ["pre_marketing"]
        if domain == "operation_management":
            return ["daily_operation"]
        return ["unspecified"]


_repository: ModelAssetRepository | None = None


def get_model_asset_repository() -> ModelAssetRepository:
    """Return singleton model asset repository."""
    global _repository
    if _repository is None:
        _repository = ModelAssetRepository()
    return _repository


def reset_model_asset_repository_for_tests() -> None:
    """Reset singleton repository in tests."""
    global _repository
    _repository = None
