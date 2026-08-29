"""Tests for scripts/refresh_official_eval_reports.py (legacy schema refresh)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "refresh_official_eval_reports.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("refresh_official_eval_reports", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_eval(split: str, rows: list[dict]) -> dict:
    total = len(rows)
    return {
        "topk_evaluation": {
            "metric": "topk_hit_rate",
            "total": total,
            "top1_hits": sum(1 for r in rows if r["top1_hit"]),
            "top3_hits": sum(1 for r in rows if r["top3_hit"]),
            "top5_hits": sum(1 for r in rows if r["top5_hit"]),
            "top3_hit_rate_pct": 0.0,
            "top5_hit_rate_pct": 0.0,
            "details": rows,
        }
    }


def _row(test_id: str, rank: int | None) -> dict:
    gold = "OFFICIAL_002"
    others = ["OFFICIAL_001", "OFFICIAL_003", "OFFICIAL_004", "OFFICIAL_005", "OFFICIAL_006"]
    ids = list(others[:5])
    if rank is not None:
        ids.insert(rank - 1, gold)
    return {
        "test_id": test_id,
        "query": "测试问题" + test_id,
        "gold_id": gold,
        "gold_name": "金标模型",
        "recommended_top5_ids": ids,
        "recommended_top5_names": ["模型" + i[-3:] for i in ids],
        "top1_hit": rank == 1,
        "top3_hit": rank is not None and rank <= 3,
        "top5_hit": rank is not None,
        "gold_rank_in_returned_top5": rank,
    }


def test_refresh_produces_legacy_schema_and_preserves_evidence(tmp_path: Path) -> None:
    module = _load_script()
    val_path = tmp_path / "val.json"
    test_path = tmp_path / "test.json"
    val_path.write_text(json.dumps(_fake_eval("val", [_row("val_0001", 1), _row("val_0002", 2)])), encoding="utf-8")
    test_path.write_text(json.dumps(_fake_eval("test", [_row("test_0001", 4), _row("test_0002", None)])), encoding="utf-8")

    output_dir = tmp_path / "official_eval"
    output_dir.mkdir()
    evidence = output_dir / "leakage_audit.json"
    evidence.write_text('{"status": "verified"}', encoding="utf-8")

    summary = module.refresh(val_path, test_path, output_dir)

    # Unrelated evidence preserved; all five owned files generated.
    assert evidence.read_text(encoding="utf-8") == '{"status": "verified"}'
    for name in module.OWNED_FILES:
        assert (output_dir / name).exists(), name

    # Summary matches the legacy schema the frontend consumes.
    for key in ("generated_at", "source", "top1_accuracy", "top3_accuracy",
                "top5_accuracy", "val", "test", "failure_attribution"):
        assert key in summary
    for block in (summary["val"], summary["test"]):
        for key in ("total", "top1_hits", "top3_hits", "top5_hits",
                    "top1_rate", "top3_rate", "top5_rate"):
            assert key in block

    # Numbers are computed from the inputs, never hand-written.
    assert summary["val"]["top1_hits"] == 1
    assert summary["val"]["top1_rate"] == 50.0
    assert summary["test"]["top5_hits"] == 1
    assert summary["test"]["top5_rate"] == 50.0

    # Results rows keep the legacy per-query shape; scores stay hidden.
    results = json.loads((output_dir / "test_results.json").read_text(encoding="utf-8"))
    row = results["results"][0]
    for key in ("query_id", "split", "query", "gold_model_ids", "gold_model_names",
                "recommended_top5", "recommended_models", "top1_hit", "top3_hit",
                "top5_hit", "failure_type"):
        assert key in row
    assert all(m["score"] == 0.0 and m["matched_keywords"] == []
               for r in results["results"] for m in r["recommended_models"])

    # Failures: rank-4 is top3_miss/confused_model; missing is top5_miss/unknown.
    failures = json.loads((output_dir / "official_failures.json").read_text(encoding="utf-8"))
    by_id = {f["query_id"]: f for f in failures}
    assert by_id["val_0002"]["failure_scope"] == "top1_miss"
    assert by_id["val_0002"]["failure_type"] == "confused_model"
    assert by_id["test_0001"]["failure_scope"] == "top3_miss"
    assert by_id["test_0002"]["failure_scope"] == "top5_miss"
    assert by_id["test_0002"]["failure_type"] == "unknown"
    assert all(f["reason"] and f["suggested_fix"] for f in failures)

    attribution = summary["failure_attribution"]
    assert attribution["test"]["unknown"] == 1
    assert attribution["total"]["confused_model"] == 2
