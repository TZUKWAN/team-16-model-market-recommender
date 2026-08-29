"""Immutable model-asset imports with quarantine, activation and rollback."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_model_assets import normalize_record, read_records, validate_imported  # noqa: E402


class AssetCatalogVersionStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.versions = root / "versions"
        self.active_path = root / "active.json"
        self.versions.mkdir(parents=True, exist_ok=True)

    def read_rows(self, version: str) -> list[dict[str, Any]]:
        path = self.versions / version / "models.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def active_version(self) -> str:
        try:
            return str(json.loads(self.active_path.read_text(encoding="utf-8"))["version"])
        except (OSError, json.JSONDecodeError, KeyError):
            return ""

    def import_path(self, input_path: Path, source: str, version: str) -> dict[str, Any]:
        target = self.versions / version
        if target.exists():
            raise ValueError(f"asset version already exists: {version}")
        accepted: list[dict[str, Any]] = []
        quarantine: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(read_records(input_path), 1):
            record = normalize_record(raw, source)
            model_id = str(record.get("model_id") or "")
            if not model_id or model_id in seen:
                quarantine.append({"row": index, "model_id": model_id, "reason": "missing_or_duplicate_id"})
                continue
            errors = validate_imported([record])
            if errors:
                quarantine.append({"row": index, "model_id": model_id, "reason": "validation_error", "errors": errors})
                continue
            seen.add(model_id)
            record["asset_version"] = version
            record["asset_status"] = "cataloged"
            accepted.append(record)

        previous_version = self.active_version()
        previous = {row.get("model_id"): row for row in self.read_rows(previous_version)}
        current = {row.get("model_id"): row for row in accepted}
        schema_changes = []
        for model_id in sorted(set(previous) & set(current)):
            for field in ("input_schema", "output_schema", "result_schema"):
                if previous[model_id].get(field) != current[model_id].get(field):
                    schema_changes.append({"model_id": model_id, "field": field})
        models_text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in accepted)
        target.mkdir(parents=True)
        (target / "models.jsonl").write_text(models_text, encoding="utf-8")
        (target / "quarantine.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in quarantine), encoding="utf-8"
        )
        manifest = {
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source": source,
            "accepted_count": len(accepted),
            "quarantine_count": len(quarantine),
            "soft_deleted_model_ids": sorted(set(previous) - set(current)),
            "schema_changes": schema_changes,
            "models_sha256": hashlib.sha256(models_text.encode("utf-8")).hexdigest(),
            "previous_version": previous_version,
        }
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.activate(version)
        return manifest

    def activate(self, version: str) -> None:
        if not (self.versions / version / "manifest.json").is_file():
            raise ValueError(f"unknown asset version: {version}")
        temporary = self.active_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": version}) + "\n", encoding="utf-8")
        temporary.replace(self.active_path)

    def rollback(self) -> str:
        current = self.active_version()
        if not current:
            raise ValueError("no active asset version")
        manifest = json.loads((self.versions / current / "manifest.json").read_text(encoding="utf-8"))
        previous = str(manifest.get("previous_version") or "")
        if not previous:
            raise ValueError("active version has no rollback target")
        self.activate(previous)
        return previous


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("import", "activate", "rollback"))
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "data" / "model_catalog")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--source", default="imported")
    parser.add_argument("--version", default="")
    args = parser.parse_args()
    store = AssetCatalogVersionStore(args.catalog_dir)
    if args.action == "import":
        if args.input is None or not args.version:
            parser.error("import requires --input and --version")
        result: Any = store.import_path(args.input, args.source, args.version)
    elif args.action == "activate":
        store.activate(args.version)
        result = {"active_version": args.version}
    else:
        result = {"active_version": store.rollback()}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
