"""Report value coverage separately from verified field provenance."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.repositories.model_asset_repository import ModelAssetRepository  # noqa: E402


FIELDS = [
    "canonical_name", "description", "domain", "customer_segment",
    "performance_metrics", "historical_cases", "input_schema", "result_schema",
]


def build_report() -> dict:
    models = ModelAssetRepository().list_models(source="official")
    coverage = {}
    for field in FIELDS:
        present = [model for model in models if model.get(field) not in (None, "", [], {})]
        verified = [
            model for model in present
            if model.get("field_provenance", {}).get(field, {}).get("verification") == "source_verified"
        ]
        source_types: dict[str, int] = {}
        for model in present:
            source_type = model.get("field_provenance", {}).get(field, {}).get("source_type", "missing")
            source_types[source_type] = source_types.get(source_type, 0) + 1
        coverage[field] = {
            "present_count": len(present),
            "present_pct": round(len(present) / len(models) * 100, 2),
            "verified_count": len(verified),
            "verified_pct": round(len(verified) / len(models) * 100, 2),
            "source_types": source_types,
        }
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "official_model_count": len(models),
        "coverage": coverage,
        "boundary": "Presence is not verification. Synthetic draft metrics and cases are not bank evidence.",
    }


def main() -> int:
    payload = build_report()
    output = ROOT / "reports" / "data_governance" / "model_field_provenance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["official_model_count"] == 60 else 2


if __name__ == "__main__":
    raise SystemExit(main())
