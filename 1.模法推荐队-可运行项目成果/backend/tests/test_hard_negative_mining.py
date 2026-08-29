"""Tests for train-only same-domain hard-negative mining."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "mine_hard_negatives.py"
    spec = importlib.util.spec_from_file_location("mine_hard_negatives", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_select_hard_negatives_keeps_only_same_domain_wrong_models():
    module = load_script()
    recommendations = [
        SimpleNamespace(model_id="B", rank=1),
        SimpleNamespace(model_id="A", rank=2),
        SimpleNamespace(model_id="C", rank=3),
        SimpleNamespace(model_id="D", rank=4),
    ]
    domains = {"A": "risk", "B": "risk", "C": "marketing", "D": "risk"}

    selected = module.select_hard_negatives(
        recommendations,
        gold_model_id="A",
        model_domains=domains,
        limit=2,
    )

    assert [item.model_id for item in selected] == ["B", "D"]


def test_mining_rejects_non_train_rows():
    module = load_script()
    with pytest.raises(ValueError, match="train rows only"):
        module.mine(
            [{"test_id": "val_0001"}],
            service=SimpleNamespace(models=[]),
            parser=SimpleNamespace(),
            negatives_per_case=1,
        )
