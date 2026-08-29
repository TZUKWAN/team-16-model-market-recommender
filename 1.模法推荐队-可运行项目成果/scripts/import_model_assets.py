"""Import model assets from JSONL/JSON/CSV/XLSX into normalized JSONL.

Examples:
    python scripts/import_model_assets.py --input data/official/model_catalog_structured.jsonl --output reports/imported_official_models.jsonl --source official
    python scripts/import_model_assets.py --input data/knowledge --output reports/imported_demo_models.jsonl --source demo
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.repositories.model_asset_repository import ModelAssetRepository  # noqa: E402
from app.services.data_loader import load_tags, load_data_fields, _adapt_official_model  # noqa: E402


LIST_FIELDS = {
    "aliases",
    "business_scenario",
    "business_stage",
    "customer_segment",
    "model_capability",
    "input_fields_required",
    "input_fields_optional",
    "output_fields",
    "historical_cases",
    "tags",
}

JSON_FIELDS = {"performance_metrics", "input_schema", "output_schema", "result_schema"}

IMPORT_FIELDS = [
    "model_id",
    "model_name",
    "canonical_name",
    "aliases",
    "source",
    "asset_version",
    "asset_status",
    "domain",
    "business_scenario",
    "business_stage",
    "customer_segment",
    "model_capability",
    "input_fields_required",
    "input_fields_optional",
    "output_fields",
    "performance_metrics",
    "applicable_conditions",
    "unsuitable_conditions",
    "compliance_boundary",
    "permission_scope",
    "legal_boundary",
    "deployment_status",
    "api_available",
    "historical_cases",
    "tags",
    "description",
    "input_schema",
    "output_schema",
    "result_schema",
]

MAX_IMPORT_FILE_BYTES = 50 * 1024 * 1024
MAX_WORKBOOK_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_IMPORT_JSON_DEPTH = 20


def _json_depth(value: Any) -> int:
    if not isinstance(value, (dict, list)) or not value:
        return 1
    children = value.values() if isinstance(value, dict) else value
    return 1 + max(_json_depth(child) for child in children)


def _validate_input_file(path: Path) -> None:
    if path.stat().st_size > MAX_IMPORT_FILE_BYTES:
        raise ValueError(f"Input file exceeds {MAX_IMPORT_FILE_BYTES} byte limit: {path}")
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        with zipfile.ZipFile(path) as archive:
            expanded = sum(item.file_size for item in archive.infolist())
        if expanded > MAX_WORKBOOK_UNCOMPRESSED_BYTES:
            raise ValueError("Workbook uncompressed content exceeds safety limit")


def _validate_json_complexity(value: Any) -> None:
    if _json_depth(value) > MAX_IMPORT_JSON_DEPTH:
        raise ValueError(f"JSON nesting exceeds {MAX_IMPORT_JSON_DEPTH} levels")


def load_reference_sets() -> tuple[set[str], set[str]]:
    tags_data = load_tags()
    valid_tags = {str(t.get("key", "")) for t in tags_data.get("tags", []) if t.get("key")}
    fields_data = load_data_fields()
    field_rows = fields_data.get("fields", []) if isinstance(fields_data, dict) else fields_data
    valid_fields = {str(f.get("field_key", "")) for f in field_rows if isinstance(f, dict) and f.get("field_key")}
    existing_repo = ModelAssetRepository()
    for model in existing_repo.list_models():
        for field_name in ("input_fields_required", "input_fields_optional", "output_fields"):
            valid_fields.update(str(v) for v in model.get(field_name, []) if v)
    return valid_tags, valid_fields


def read_records(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        records: list[dict[str, Any]] = []
        for fp in sorted(path.glob("*.json")):
            if fp.name in {"tags.json", "data_fields.json", "composition_templates.json"}:
                continue
            _validate_input_file(fp)
            data = json.loads(fp.read_text(encoding="utf-8"))
            _validate_json_complexity(data)
            if isinstance(data, dict) and data.get("model_id"):
                records.append(data)
        return records
    suffix = path.suffix.lower()
    _validate_input_file(path)
    if suffix == ".jsonl":
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        _validate_json_complexity(records)
        return records
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        _validate_json_complexity(data)
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        if isinstance(data, dict):
            return [data]
        raise ValueError(f"Unsupported JSON root type: {type(data).__name__}")
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [dict(row) for row in csv.DictReader(f)]
    if suffix in {".xlsx", ".xlsm"}:
        try:
            import openpyxl
        except ImportError as exc:
            raise RuntimeError("Reading .xlsx requires openpyxl>=3.1.0") from exc
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        records = []
        for row in rows[1:]:
            item = {
                headers[i]: row[i]
                for i in range(min(len(headers), len(row)))
                if headers[i]
            }
            if any(v not in (None, "") for v in item.values()):
                records.append(item)
        return records
    raise ValueError(f"Unsupported input format: {path.suffix}")


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "是", "可用", "available"}


def parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                result.append(json.dumps(item, ensure_ascii=False))
            else:
                text = str(item).strip()
                if text:
                    result.append(text)
        return result
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            return parse_list(data)
        except json.JSONDecodeError:
            pass
    for sep in ["|", "；", ";", "，", ",", "、"]:
        text = text.replace(sep, "\n")
    return [part.strip() for part in text.splitlines() if part.strip()]


def parse_json_field(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    text = str(value).strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_record(raw: dict[str, Any], source: str) -> dict[str, Any]:
    raw_source = str(raw.get("source") or source)
    if raw_source == "official" and "canonical_name" in raw and "business_stage" not in raw:
        raw = _adapt_official_model(raw)

    record: dict[str, Any] = {}
    for field in IMPORT_FIELDS:
        value = raw.get(field)
        if value in (None, ""):
            continue
        if field in LIST_FIELDS:
            record[field] = parse_list(value)
        elif field in JSON_FIELDS:
            record[field] = parse_json_field(value)
        elif field == "api_available":
            record[field] = parse_bool(value)
        else:
            record[field] = str(value).strip()

    if not record.get("model_name") and record.get("canonical_name"):
        record["model_name"] = record["canonical_name"]
    if not record.get("canonical_name") and record.get("model_name"):
        record["canonical_name"] = record["model_name"]
    record["source"] = record.get("source") or source
    record["asset_version"] = record.get("asset_version") or "1.0.0"
    return record


def validate_imported(records: list[dict[str, Any]]) -> list[str]:
    valid_tags, valid_fields = load_reference_sets()
    repo = ModelAssetRepository(raw_models=records)
    errors = [
        f"{issue.model_id}.{issue.field}: {issue.message}"
        for issue in repo.validation_issues()
    ]

    for record in records:
        model_id = record.get("model_id", "<missing>")
        for tag in record.get("tags", []):
            if tag and tag not in valid_tags:
                errors.append(f"{model_id}.tags: unknown tag '{tag}'")
        for field_name in ("input_fields_required", "input_fields_optional", "output_fields"):
            for value in record.get(field_name, []):
                if value and value not in valid_fields:
                    errors.append(f"{model_id}.{field_name}: unknown field '{value}'")
    return errors


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import model assets into normalized JSONL.")
    parser.add_argument("--input", required=True, help="Input .jsonl/.json/.csv/.xlsx file or demo JSON directory.")
    parser.add_argument("--output", required=True, help="Output normalized JSONL path.")
    parser.add_argument("--source", default="imported", help="Default source for rows missing source.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing output.")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.is_absolute():
        input_path = BASE_DIR / input_path
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path

    raw_records = read_records(input_path)
    records = [normalize_record(record, args.source) for record in raw_records]
    errors = validate_imported(records)

    print("MODEL ASSET IMPORT")
    print("=" * 60)
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Records: {len(records)}")
    print(f"Validation errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for error in errors[:100]:
            print(f"- {error}")
        if len(errors) > 100:
            print(f"... {len(errors) - 100} more")
        return 1

    if args.dry_run:
        print("\n[PASS] Dry run succeeded; output was not written.")
        return 0

    write_jsonl(records, output_path)
    print("\n[PASS] Import succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
