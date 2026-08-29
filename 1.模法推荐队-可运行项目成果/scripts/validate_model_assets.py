"""Validate normalized model assets from ModelAssetRepository.

Usage:
    python scripts/validate_model_assets.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = BASE_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.repositories.model_asset_repository import ModelAssetRepository  # noqa: E402
from import_model_assets import validate_imported  # noqa: E402


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate normalized model assets.")
    parser.add_argument("--input", help="Optional normalized JSONL file to validate instead of repository data.")
    args = parser.parse_args(argv)

    if args.input:
        input_path = Path(args.input)
        if not input_path.is_absolute():
            input_path = BASE_DIR / input_path
        records = _read_jsonl(input_path)
        repo = ModelAssetRepository(raw_models=records)
    else:
        input_path = None
        records = None
        repo = ModelAssetRepository()

    stats = repo.stats()
    issues = [] if records is not None else repo.validation_issues()
    import_errors = validate_imported(records) if records is not None else []

    print("MODEL ASSET VALIDATION")
    print("=" * 60)
    if input_path:
        print(f"Input: {input_path}")
    print(f"Total models: {stats.total_models}")
    print(f"By source: {stats.by_source}")
    print(f"By domain: {stats.by_domain}")
    print(f"API available: {stats.api_available}")
    print(f"Validation issues: {len(issues) + len(import_errors)}")

    if issues or import_errors:
        print("\nIssues:")
        for issue in issues:
            print(
                f"- [{issue.severity}] {issue.model_id} "
                f"{issue.field}: {issue.message}"
            )
        for error in import_errors:
            print(f"- [error] {error}")
        return 1

    print("\n[PASS] Model asset repository is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
