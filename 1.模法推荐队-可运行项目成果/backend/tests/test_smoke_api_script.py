"""Tests for the API smoke script."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "smoke_api.py"
    spec = importlib.util.spec_from_file_location("smoke_api", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_smoke_scenarios_are_five_business_paths():
    module = load_script()

    assert len(module.SCENARIOS) == 5
    assert {scenario["id"] for scenario in module.SCENARIOS} == {
        "marketing_first_loan",
        "pre_loan_risk",
        "post_loan_warning",
        "branch_operation",
        "churn_retention",
    }


def test_in_process_smoke_single_scenario_passes():
    module = load_script()

    report = module.run_smoke(limit=1)

    assert report["mode"] == "in_process"
    assert report["scenario_count"] == 1
    assert report["passed"] is True
    assert report["failed_count"] == 0
