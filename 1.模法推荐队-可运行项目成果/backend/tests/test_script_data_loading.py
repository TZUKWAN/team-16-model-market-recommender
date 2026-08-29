"""Regression tests for shared project data loaders."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_data_module():
    path = ROOT / "scripts" / "load_data.py"
    spec = importlib.util.spec_from_file_location("project_load_data", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_explanation_survey_loader_accepts_utf8_bom():
    survey = load_data_module().load_explanation_survey()

    assert isinstance(survey, dict)
    assert survey
