"""Tests for LLM-as-Judge explanation evaluation script."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "run_explanation_judge_with_llm.py"
    spec = importlib.util.spec_from_file_location("run_explanation_judge_with_llm", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_validate_judge_payload_accepts_complete_scores():
    module = load_script()

    result = module.validate_judge_payload({
        "scores": {
            "relevance": 5,
            "completeness": 4,
            "traceability": 4,
            "compliance": 5,
            "readability": 5,
        },
        "overall_comment": "解释清晰且可追溯。",
        "risk_flags": ["无明显问题"],
    })

    assert result["scores"]["relevance"] == 5
    assert result["risk_flags"] == ["无明显问题"]


def test_unavailable_judge_skips_without_fake_scores():
    module = load_script()

    class UnavailableLLM:
        available = False

    report = module.judge_cases([{"case_id": "case_1"}], llm_client=UnavailableLLM())

    assert report["status"] == "skipped"
    assert report["results"] == []


def test_fake_judge_returns_summary():
    module = load_script()

    class FakeLLM:
        available = True
        last_trace_id = "judge_trace_1"

        def chat_json(self, system_prompt, user_message, temperature=0.1):
            return {
                "scores": {
                    "relevance": 5,
                    "completeness": 4,
                    "traceability": 4,
                    "compliance": 5,
                    "readability": 5,
                },
                "overall_comment": "解释能对应模型事实。",
                "risk_flags": [],
            }

    cases = [{
        "case_id": "case_1",
        "query": "帮我找首贷营销模型。",
        "recommendation": {
            "model_id": "OFFICIAL_001",
            "model_name": "示例模型",
        },
    }]
    report = module.judge_cases(cases, llm_client=FakeLLM())

    assert report["status"] == "completed"
    assert report["judged_count"] == 1
    assert report["overall_average"] == 4.6
    assert report["results"][0]["trace_id"] == "judge_trace_1"

def test_build_cases_expands_explanation_eval_audiences():
    module = load_script()

    cases = module.build_cases(limit=0, top_n=1)

    assert len(cases) == 30
    assert {case["target_audience"] for case in cases} == {"business", "technical", "management"}
    assert all(case["source_dataset"] == "data/eval/explanation_eval.jsonl" for case in cases)
    assert all(case["explanation_text"] for case in cases)
    assert all(case["recommendation"]["model_id"].split("_", 1)[0] in {"RISK", "MKT", "OPS"} for case in cases)
