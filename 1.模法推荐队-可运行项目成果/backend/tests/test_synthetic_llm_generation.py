"""Tests for LLM-enhanced synthetic data generation boundaries."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "generate_synthetic_with_llm.py"
    spec = importlib.util.spec_from_file_location("generate_synthetic_with_llm", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_extract_queries_accepts_strings_and_dicts():
    module = load_script()

    queries = module.extract_queries({
        "queries": [
            "帮我找一个能做AUM流失预警的模型。",
            {"query": "客户经理想筛高潜财富客户，应该用哪个模型？"},
            {"user_query": "太短"},
            123,
        ]
    })

    assert queries == [
        "帮我找一个能做AUM流失预警的模型。",
        "客户经理想筛高潜财富客户，应该用哪个模型？",
    ]


def test_dry_run_records_are_not_labeled_as_live_llm():
    module = load_script()

    records = module.generate_records(per_model=2, limit_models=2, dry_run_template=True)

    assert len(records) == 4
    assert {row["source"] for row in records} == {module.DRY_RUN_SOURCE}
    assert module.LIVE_SOURCE not in {row["source"] for row in records}
    assert all(row["review_sample_required"] is True for row in records)
    assert all(row["local_validation"]["model_id_valid"] is True for row in records)
    assert len({row["query_hash"] for row in records}) == len(records)


def test_unavailable_live_llm_returns_no_records_without_faking():
    module = load_script()

    class UnavailableLLM:
        available = False

    records = module.generate_records(
        per_model=1,
        limit_models=1,
        dry_run_template=False,
        llm_client=UnavailableLLM(),
    )

    assert records == []
