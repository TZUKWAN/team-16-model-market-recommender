"""Tests for robustness dataset generation and evaluation scripts."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_generate_robust_eval_builds_five_perturbations():
    module = load_script("generate_robust_eval.py")
    records = module.generate(limit=2)

    assert len(records) == 10
    assert {record["perturbation_type"] for record in records} == {
        "synonym",
        "colloquial",
        "typo_noise",
        "long_context",
        "mixed_context",
    }
    assert all(record["gold_model_id"] for record in records)
    assert len({record["query"] for record in records}) == len(records)


def test_run_robust_eval_returns_metrics_shape():
    generator = load_script("generate_robust_eval.py")
    evaluator = load_script("run_robust_eval.py")
    records = generator.generate(limit=1)

    result = evaluator.evaluate(records, limit=3)

    assert result["dataset_size"] == 3
    assert "overall" in result["metrics"]
    assert "intent_accuracy_pct" in result["metrics"]["overall"]
    assert "top3_hit_rate_pct" in result["metrics"]["overall"]
    assert "top5_hit_rate_pct" in result["metrics"]["overall"]
