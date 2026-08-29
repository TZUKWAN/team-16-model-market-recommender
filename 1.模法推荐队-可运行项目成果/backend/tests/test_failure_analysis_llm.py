"""Tests for LLM-assisted failure analysis reports."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "analyze_failures_with_llm.py"
spec = importlib.util.spec_from_file_location("analyze_failures_with_llm", SCRIPT_PATH)
failure_script = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(failure_script)


class FakeLLM:
    available = True
    last_trace_id = "llm_failure_trace"

    def chat_json(self, system_prompt, user_message, temperature=0.0):
        assert "api_key" not in user_message.lower()
        return {
            "category": "tag_missing",
            "summary": "预测标签未覆盖 gold 标签，导致后续召回证据不足。",
            "suggested_action": "补充该业务描述对应的标签同义词并复测。",
        }


class UnavailableLLM:
    available = False
    last_trace_id = ""


def test_collect_failures_keeps_original_gold_and_pred_fields():
    results = {
        "intent_evaluation": {
            "details": [
                {
                    "test_id": "intent_1",
                    "query": "客户流失预警",
                    "gold_domain": "customer_marketing",
                    "predicted": "credit_risk",
                    "correct": False,
                }
            ]
        },
        "tag_evaluation": {
            "details": [
                {
                    "test_id": "tag_1",
                    "query": "AUM 提升",
                    "gold_tags": ["aum_growth"],
                    "predicted_tags": ["credit_risk"],
                    "has_overlap": False,
                }
            ]
        },
        "topk_evaluation": {
            "details": [
                {
                    "test_id": "topk_1",
                    "query": "阳光E贷准入评分",
                    "gold_id": "OFFICIAL_010",
                    "gold_name": "阳光E贷准入评分模型",
                    "recommended_top5_ids": ["OFFICIAL_011"],
                    "recommended_top5_names": ["其他模型"],
                    "top3_hit": False,
                    "top5_hit": False,
                }
            ]
        },
    }

    failures = failure_script.collect_failures(results, max_samples=10)

    assert len(failures) == 3
    assert failures[0]["sample_id"] == "intent_1"
    assert failures[0]["gold"]["domain"] == "customer_marketing"
    assert failures[0]["pred"]["domain"] == "credit_risk"
    assert failures[2]["gold"]["model_id"] == "OFFICIAL_010"
    assert failures[2]["pred"]["recommended_top5_ids"] == ["OFFICIAL_011"]


def test_llm_analysis_and_report_do_not_include_secrets(tmp_path):
    failure = {
        "sample_id": "tag_1",
        "source_eval": "tag",
        "query": "AUM 提升",
        "gold": {"tags": ["aum_growth"]},
        "pred": {"tags": ["credit_risk"]},
        "rule_category": "tag_missing",
    }

    analysis = failure_script.analyze_failure_with_llm(failure, FakeLLM())
    report = failure_script.build_report([failure], [analysis], tmp_path / "eval.json")
    json_path, md_path = failure_script.write_reports(report, tmp_path)

    assert analysis["analysis_source"] == "llm"
    assert analysis["category"] == "tag_missing"
    assert analysis["llm_trace_id"] == "llm_failure_trace"
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    source_file = loaded["source_file"]
    source_path = Path(source_file)
    assert source_path.name == "eval.json"
    assert not source_path.is_absolute()
    assert ".." not in source_path.parts
    assert loaded["failures"][0]["sample_id"] == "tag_1"
    text = json_path.read_text(encoding="utf-8") + md_path.read_text(encoding="utf-8")
    assert "api_key" not in text.lower()
    assert "secret" not in text.lower()


def test_unavailable_llm_records_rule_fallback():
    failure = {
        "sample_id": "comp_1",
        "source_eval": "composition",
        "query": "贷前贷中贷后全流程",
        "gold": {"model_ids": ["OFFICIAL_001"]},
        "pred": {"composition_score": 55.0},
        "rule_category": "composition_chain_incomplete",
    }

    analysis = failure_script.analyze_failure_with_llm(failure, UnavailableLLM())

    assert analysis["analysis_source"] == "rule_fallback"
    assert analysis["category"] == "composition_chain_incomplete"
    assert analysis["summary"]
