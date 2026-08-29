"""
Official evaluation API endpoints.
Provides read-only access to official evaluation reports and dataset metadata.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _find_project_root() -> Path:
    """Walk up from this file until data/ and reports/ directories are found."""
    path = Path(__file__).resolve()
    for _ in range(10):
        if (path / "data").is_dir() and (path / "reports").is_dir():
            return path
        path = path.parent
    # Fallback: hardcoded relative path from v1/official_evaluation.py (5 levels up)
    return Path(__file__).resolve().parent.parent.parent.parent.parent


_PROJECT_ROOT = _find_project_root()
REPORTS_DIR = _PROJECT_ROOT / "reports" / "official_eval"
DATA_DIR = _PROJECT_ROOT / "data" / "official_60"


@router.get("/official-evaluation/summary")
async def get_official_summary():
    """Get official TopK evaluation summary."""
    path = REPORTS_DIR / "official_topk_summary.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Official evaluation summary not found. "
                "Run: python scripts/evaluate_official_topk.py"
            ),
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/official-evaluation/results")
async def get_official_results(
    split: str = Query(..., description="Split name: val or test"),
):
    """Get evaluation results for a given split (val/test)."""
    split_lower = split.strip().lower()
    if split_lower not in ("val", "test"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid split '{split}'. Must be 'val' or 'test'.",
        )
    path = REPORTS_DIR / f"{split_lower}_results.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Results for split '{split_lower}' not found. "
                "Run: python scripts/evaluate_official_topk.py"
            ),
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/official-evaluation/failures")
async def get_official_failures(
    split: str | None = Query(
        default=None, description="Filter by split (val/test)"
    ),
    failure_type: str | None = Query(
        default=None, description="Filter by failure type (e.g., keyword_missing)"
    ),
):
    """Get evaluation failures, optionally filtered by split and/or failure_type."""
    path = REPORTS_DIR / "official_failures.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Official evaluation failures not found. "
                "Run: python scripts/evaluate_official_topk.py"
            ),
        )
    failures: list[dict] = json.loads(path.read_text(encoding="utf-8"))

    if split is not None:
        split_lower = split.strip().lower()
        failures = [f for f in failures if f.get("split", "").lower() == split_lower]

    if failure_type is not None:
        failures = [
            f for f in failures if f.get("failure_type", "") == failure_type
        ]

    return failures


@router.get("/official-evaluation/dataset")
async def get_official_dataset():
    """Get official dataset manifest and statistics."""
    manifest_path = DATA_DIR / "dataset_manifest.json"
    models_path = DATA_DIR / "models.jsonl"

    if not manifest_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Dataset manifest not found. "
                "Run: python scripts/prepare_official_dataset.py"
            ),
        )
    if not models_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Models file not found. "
                "Run: python scripts/prepare_official_dataset.py"
            ),
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    model_count = manifest.get("model_count") or sum(
        1 for _ in models_path.open(encoding="utf-8")
    )
    query_count = manifest.get("query_count", 0)

    split_counts = manifest.get("split_counts", {})
    splits = {
        "train": split_counts.get("train", 0),
        "val": split_counts.get("val", 0),
        "test": split_counts.get("test", 0),
    }

    return {
        "manifest": manifest,
        "model_count": model_count,
        "query_count": query_count,
        "splits": splits,
    }
