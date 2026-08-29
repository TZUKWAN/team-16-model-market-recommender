"""Migrate feature-v1 official model IDs to the canonical official-v1 catalog.

The feature branch assigned IDs after sorting model names, while the official
dataset branch assigned IDs by source Excel row.  Those namespaces reuse the
same ``OFFICIAL_NNN`` strings for different models, so this migration must run
once with an explicit catalog-version context.  Re-running a string mapping on
already migrated files would corrupt valid canonical IDs; an existing mapping
therefore switches this script into validation-only mode.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MODELS = ROOT / "data" / "official_60" / "models.jsonl"
FEATURE_CATALOG = ROOT / "data" / "official" / "model_catalog_raw.jsonl"
MAPPING_PATH = ROOT / "data" / "official_60" / "official_id_mapping.json"
REPORT_PATH = ROOT / "reports" / "data_governance" / "official_id_migration_report.json"

MIGRATION_ROOTS = (
    ROOT / "data" / "official",
    ROOT / "data" / "eval_official",
    ROOT / "data" / "eval_robustness",
    ROOT / "data" / "eval_synthetic",
    ROOT / "data" / "knowledge",
    ROOT / "data" / "synthetic",
    ROOT / "data" / "synthetic_llm",
    ROOT / "data" / "training",
)

OFFICIAL_ID_RE = re.compile(r"OFFICIAL_\d{3}")
SOURCE_REF = "origin/feature/llm-driven-upgrade"


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(value))).strip()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def canonical_catalog() -> tuple[dict[str, str], set[str]]:
    rows = load_jsonl(CANONICAL_MODELS)
    if len(rows) != 60:
        raise ValueError(f"Expected 60 canonical models, found {len(rows)}")
    by_name: dict[str, str] = {}
    ids: set[str] = set()
    for row in rows:
        model_id = str(row.get("model_id", ""))
        name = normalize_name(str(row.get("model_name", "")))
        if not model_id or not name or name in by_name or model_id in ids:
            raise ValueError(f"Invalid or duplicate canonical row: {row}")
        by_name[name] = model_id
        ids.add(model_id)
    return by_name, ids


def build_mapping(canonical_by_name: dict[str, str]) -> list[dict[str, str]]:
    feature_rows = load_jsonl(FEATURE_CATALOG)
    if len(feature_rows) != 60:
        raise ValueError(f"Expected 60 feature models, found {len(feature_rows)}")

    entries: list[dict[str, str]] = []
    seen_names: set[str] = set()
    seen_feature_ids: set[str] = set()
    for row in feature_rows:
        name_value = str(row.get("canonical_name") or row.get("model_name") or "")
        name = normalize_name(name_value)
        old_id = str(row.get("model_id", ""))
        if not name or name in seen_names or not old_id or old_id in seen_feature_ids:
            raise ValueError(f"Invalid or duplicate feature row: {row}")
        if name not in canonical_by_name:
            raise ValueError(f"Feature model has no canonical match: {name_value}")
        seen_names.add(name)
        seen_feature_ids.add(old_id)
        entries.append(
            {
                "from_catalog": "feature-v1",
                "from_id": old_id,
                "to_catalog": "official-v1",
                "to_id": canonical_by_name[name],
                "canonical_name": name_value,
            }
        )

    if seen_names != set(canonical_by_name):
        missing = sorted(set(canonical_by_name) - seen_names)
        raise ValueError(f"Canonical models missing from feature catalog: {missing}")
    return sorted(entries, key=lambda item: item["from_id"])


def replace_ids(value: Any, mapping: dict[str, str]) -> tuple[Any, int]:
    if isinstance(value, str):
        count = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal count
            original = match.group(0)
            replacement = mapping.get(original, original)
            if replacement != original:
                count += 1
            return replacement

        return OFFICIAL_ID_RE.sub(replace, value), count
    if isinstance(value, list):
        output: list[Any] = []
        total = 0
        for item in value:
            migrated, count = replace_ids(item, mapping)
            output.append(migrated)
            total += count
        return output, total
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        total = 0
        for key, item in value.items():
            migrated_key, key_count = replace_ids(key, mapping)
            migrated, count = replace_ids(item, mapping)
            if migrated_key in output:
                raise ValueError(f"ID migration produced duplicate JSON key: {migrated_key}")
            output[migrated_key] = migrated
            total += key_count + count
        return output, total
    return value, 0


def iter_migration_files() -> list[Path]:
    paths: list[Path] = []
    for root in MIGRATION_ROOTS:
        if not root.exists():
            continue
        paths.extend(path for path in root.rglob("*.json") if path != MAPPING_PATH)
        paths.extend(root.rglob("*.jsonl"))
    return sorted(set(paths))


def migrate_files(mapping: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    migrated_files: list[dict[str, Any]] = []
    total_replacements = 0
    for path in iter_migration_files():
        if path.suffix == ".jsonl":
            value: Any = load_jsonl(path)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
        migrated, replacements = replace_ids(value, mapping)
        if replacements:
            if path.suffix == ".jsonl":
                write_jsonl(path, migrated)
            else:
                write_json(path, migrated)
            migrated_files.append(
                {"path": path.relative_to(ROOT).as_posix(), "replacements": replacements}
            )
            total_replacements += replacements
    return migrated_files, total_replacements


def source_replacement_manifest(mapping: dict[str, str]) -> tuple[list[dict[str, Any]], int]:
    """Reconstruct the one-time migration counts from the frozen feature ref."""
    migrated_files: list[dict[str, Any]] = []
    total_replacements = 0
    for path in iter_migration_files():
        relative = path.relative_to(ROOT).as_posix()
        result = subprocess.run(
            ["git", "show", f"{SOURCE_REF}:{relative}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            continue
        replacements = sum(
            1
            for model_id in OFFICIAL_ID_RE.findall(result.stdout)
            if mapping.get(model_id, model_id) != model_id
        )
        if replacements:
            migrated_files.append({"path": relative, "replacements": replacements})
            total_replacements += replacements
    return migrated_files, total_replacements


def add_catalog_versions() -> None:
    for path in (
        ROOT / "data" / "official" / "model_catalog_raw.jsonl",
        ROOT / "data" / "official" / "model_catalog_structured.jsonl",
        ROOT / "data" / "official" / "questions_all.jsonl",
        ROOT / "data" / "official" / "questions_train.jsonl",
        ROOT / "data" / "official" / "questions_val.jsonl",
        ROOT / "data" / "official" / "questions_test.jsonl",
    ):
        rows = load_jsonl(path)
        changed = False
        for row in rows:
            if row.get("catalog_version") != "official-v1":
                row["catalog_version"] = "official-v1"
                changed = True
        if changed:
            write_jsonl(path, rows)


def rebuild_name_map() -> None:
    """Rebuild both directions from the canonical row-order catalog."""
    existing_path = ROOT / "data" / "official" / "model_name_map.json"
    existing = json.loads(existing_path.read_text(encoding="utf-8"))
    canonical_rows = load_jsonl(CANONICAL_MODELS)
    name_to_id = {
        str(row["model_name"]): str(row["model_id"])
        for row in canonical_rows
    }
    id_to_name = {model_id: name for name, model_id in name_to_id.items()}
    existing["model_name_to_id"] = dict(sorted(name_to_id.items()))
    existing["id_to_name"] = dict(sorted(id_to_name.items()))
    existing["catalog_version"] = "official-v1"
    write_json(existing_path, existing)


def validate(canonical_by_name: dict[str, str], canonical_ids: set[str]) -> dict[str, int]:
    structured = load_jsonl(ROOT / "data" / "official" / "model_catalog_structured.jsonl")
    if len(structured) != 60:
        raise ValueError(f"Expected 60 structured models, found {len(structured)}")
    for row in structured:
        name = normalize_name(str(row.get("canonical_name") or row.get("model_name") or ""))
        if canonical_by_name.get(name) != row.get("model_id"):
            raise ValueError(f"Catalog ID/name mismatch: {row}")
        if row.get("catalog_version") != "official-v1":
            raise ValueError(f"Catalog version missing: {row.get('model_id')}")

    questions = load_jsonl(ROOT / "data" / "official" / "questions_all.jsonl")
    if len(questions) != 417:
        raise ValueError(f"Expected 417 official questions, found {len(questions)}")
    for row in questions:
        name = normalize_name(str(row.get("gold_model_name", "")))
        expected = canonical_by_name.get(name)
        if not expected or row.get("gold_model_id") != expected:
            raise ValueError(f"Question ID/name mismatch: {row.get('question_id')}")
        if row.get("catalog_version") != "official-v1":
            raise ValueError(f"Question catalog version missing: {row.get('question_id')}")

    combo_rows = load_jsonl(
        ROOT / "data" / "eval_official" / "combo_eval_official_manual.jsonl"
    )
    if len(combo_rows) != 30:
        raise ValueError(f"Expected 30 official composition cases, found {len(combo_rows)}")
    combo_gold_pairs = 0
    for row in combo_rows:
        model_ids = row.get("gold_model_ids", [])
        model_names = row.get("gold_model_names", [])
        if len(model_ids) != len(model_names):
            raise ValueError(f"Composition gold pair count mismatch: {row.get('case_id')}")
        for model_id, model_name in zip(model_ids, model_names, strict=True):
            combo_gold_pairs += 1
            expected = canonical_by_name.get(normalize_name(str(model_name)))
            if not expected or model_id != expected:
                raise ValueError(
                    f"Composition ID/name mismatch: {row.get('case_id')} {model_id}"
                )

    name_map = json.loads(
        (ROOT / "data" / "official" / "model_name_map.json").read_text(encoding="utf-8")
    )
    if name_map.get("catalog_version") != "official-v1":
        raise ValueError("Model name map catalog version is missing")
    expected_name_to_id = {
        str(row["model_name"]): str(row["model_id"])
        for row in load_jsonl(CANONICAL_MODELS)
    }
    if name_map.get("model_name_to_id") != dict(sorted(expected_name_to_id.items())):
        raise ValueError("model_name_to_id does not match the canonical catalog")
    expected_id_to_name = {model_id: name for name, model_id in expected_name_to_id.items()}
    if name_map.get("id_to_name") != dict(sorted(expected_id_to_name.items())):
        raise ValueError("id_to_name does not match the canonical catalog")

    dangling: list[tuple[str, str]] = []
    scanned_ids = 0
    for path in iter_migration_files():
        text = path.read_text(encoding="utf-8")
        for model_id in OFFICIAL_ID_RE.findall(text):
            scanned_ids += 1
            if model_id not in canonical_ids:
                dangling.append((path.relative_to(ROOT).as_posix(), model_id))
    if dangling:
        raise ValueError(f"Dangling official IDs: {dangling[:10]}")
    return {
        "canonical_models": len(canonical_ids),
        "structured_models": len(structured),
        "official_questions": len(questions),
        "official_composition_cases": len(combo_rows),
        "official_composition_gold_pairs": combo_gold_pairs,
        "scanned_official_id_references": scanned_ids,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate an existing migration without changing data files.",
    )
    args = parser.parse_args()

    canonical_by_name, canonical_ids = canonical_catalog()
    migrated_files: list[dict[str, Any]] = []
    replacements = 0

    if MAPPING_PATH.exists():
        mapping_document = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
        entries = mapping_document.get("entries", [])
        if not args.check:
            raise RuntimeError(
                "Mapping already exists; refusing a second migration. Use --check instead."
            )
        old_to_new = {item["from_id"]: item["to_id"] for item in entries}
        migrated_files, replacements = source_replacement_manifest(old_to_new)
    else:
        if args.check:
            raise RuntimeError("Mapping does not exist; run migration without --check first.")
        entries = build_mapping(canonical_by_name)
        mapping_document = {
            "from_catalog": "feature-v1",
            "to_catalog": "official-v1",
            "model_count": len(entries),
            "changed_id_count": sum(1 for item in entries if item["from_id"] != item["to_id"]),
            "entries": entries,
        }
        write_json(MAPPING_PATH, mapping_document)
        old_to_new = {item["from_id"]: item["to_id"] for item in entries}
        migrated_files, replacements = migrate_files(old_to_new)
        add_catalog_versions()
        rebuild_name_map()

    if len(entries) != 60:
        raise ValueError(f"Expected 60 mapping entries, found {len(entries)}")
    stats = validate(canonical_by_name, canonical_ids)
    report = {
        "status": "validated",
        "from_catalog": "feature-v1",
        "to_catalog": "official-v1",
        "mapping_entries": len(entries),
        "changed_id_count": sum(1 for item in entries if item["from_id"] != item["to_id"]),
        "migrated_files": migrated_files,
        "replacement_count": replacements,
        "source_ref": SOURCE_REF,
        **stats,
    }
    write_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
