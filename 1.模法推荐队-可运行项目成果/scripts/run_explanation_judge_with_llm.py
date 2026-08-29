#!/usr/bin/env python3
"""Run LLM-as-Judge development evaluation for recommendation explanations.

The judge is only a development aid. It never replaces official metrics and it
must score only from the supplied demand, model facts, and explanation text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
EVAL_DIR = BASE_DIR / "data" / "eval"
REPORT_DIR = BASE_DIR / "reports" / "llm_judge"

sys.path.insert(0, str(BACKEND_DIR))

from app.services.demand_parser import DemandParser  # noqa: E402
from app.services.explanation_generator import ExplanationGenerator  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402
from app.services.recommender import ModelRecommendationService  # noqa: E402


DIMENSIONS = ["relevance", "completeness", "traceability", "compliance", "readability"]
AUDIENCE_LABELS = {
    "business": "银行一线业务人员（非技术背景）",
    "technical": "数据科学或 IT 技术人员",
    "management": "银行管理层人员",
}
JUDGE_SYSTEM_PROMPT = """你是银行模型市场推荐解释质量评审员。
只能依据用户需求、目标受众、需求解析结果、模型事实、评分证据和解释文本评分。
禁止引入外部知识；禁止因为模型名称看起来熟悉而加分；禁止评价推荐算法整体命中率。

请按以下 5 个维度各给 1-5 分：
1. relevance：解释是否回应用户需求和目标受众关注点。
2. completeness：是否覆盖场景、输出、数据要求、适用边界等关键信息。
3. traceability：解释是否能从给定模型事实和评分证据追溯。
4. compliance：是否包含或不违背合规、适用边界、人工审核提示。
5. readability：目标受众是否容易读懂。

只输出 JSON，格式如下：
{"scores":{"relevance":1,"completeness":1,"traceability":1,"compliance":1,"readability":1},"overall_comment":"一句话理由","risk_flags":["可选问题"]}
"""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_cases(limit: int = 30, top_n: int = 1) -> list[dict[str, Any]]:
    samples = load_jsonl(EVAL_DIR / "explanation_eval.jsonl")
    parser = DemandParser()
    recommender = ModelRecommendationService()
    cases: list[dict[str, Any]] = []

    for sample in samples:
        query = sample.get("raw_text") or sample.get("query") or ""
        if not query:
            continue
        target_audiences = sample.get("target_audiences") or ["business", "technical", "management"]
        # Build evaluation cases deterministically; only the judge step uses the live LLM.
        parse_result = parser.parse(query, use_llm=False)
        parse_dict = parse_result.model_dump()
        parse_dict["model_source"] = "demo"
        response = recommender.recommend(parse_dict, top_k=max(top_n, 1), use_llm=False)
        for recommendation in response.recommendations[:top_n]:
            explanations = ExplanationGenerator.generate_model_explanations(recommendation, parse_dict)
            score_breakdown = recommendation.score_breakdown.model_dump()
            evidence_cards = [card.model_dump() for card in recommendation.evidence_cards[:3]]
            for audience in target_audiences:
                audience_key = str(audience)
                explanation_text = explanations.get(audience_key) or recommendation.recommendation_reason
                cases.append({
                    "case_id": f"{sample.get('demand_id', 'case')}_{recommendation.rank}_{audience_key}",
                    "source_dataset": "data/eval/explanation_eval.jsonl",
                    "query": query,
                    "target_audience": audience_key,
                    "target_audience_label": AUDIENCE_LABELS.get(audience_key, audience_key),
                    "parse_result": {
                        "intent": parse_result.intent,
                        "business_scenario": parse_result.business_scenario,
                        "tags": parse_result.tags,
                        "expected_outputs": parse_result.expected_outputs,
                        "data_conditions": parse_result.data_conditions,
                    },
                    "recommendation": {
                        "rank": recommendation.rank,
                        "model_id": recommendation.model_id,
                        "model_name": recommendation.model_name,
                        "total_score": recommendation.total_score,
                        "score_breakdown": score_breakdown,
                        "recommendation_reason": recommendation.recommendation_reason,
                        "required_data": recommendation.required_data,
                        "missing_data": recommendation.missing_data,
                        "output_fields": recommendation.output_fields,
                        "applicable_boundary": recommendation.applicable_boundary,
                        "unsuitable_conditions": recommendation.unsuitable_conditions,
                        "compliance_notes": recommendation.compliance_notes,
                        "evidence_cards": evidence_cards,
                    },
                    "explanation_text": explanation_text,
                })

    return cases[:limit] if limit and limit > 0 else cases


def validate_judge_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, dict):
        return None
    scores: dict[str, int] = {}
    for dimension in DIMENSIONS:
        try:
            score = int(raw_scores.get(dimension))
        except (TypeError, ValueError):
            return None
        if score < 1 or score > 5:
            return None
        scores[dimension] = score
    risk_flags = payload.get("risk_flags", [])
    if not isinstance(risk_flags, list):
        risk_flags = []
    return {
        "scores": scores,
        "overall_comment": str(payload.get("overall_comment", ""))[:240],
        "risk_flags": [str(item)[:120] for item in risk_flags[:5]],
    }


def judge_cases(cases: list[dict[str, Any]], llm_client: LLMClient | None = None) -> dict[str, Any]:
    client = llm_client or LLMClient()
    if not getattr(client, "available", False):
        return {
            "status": "skipped",
            "reason": "live LLM judge requires configured environment",
            "case_count": len(cases),
            "results": [],
        }

    results: list[dict[str, Any]] = []
    invalid_cases: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        print(f"Judging {index}/{len(cases)}: {case['case_id']}", flush=True)
        payload = client.chat_json(JUDGE_SYSTEM_PROMPT, json.dumps(case, ensure_ascii=False), temperature=0.1)
        validated = validate_judge_payload(payload)
        if not validated:
            invalid_cases.append({"case_id": case["case_id"], "error": "invalid_judge_payload"})
            continue
        results.append({
            "case_id": case["case_id"],
            "query": case["query"],
            "target_audience": case.get("target_audience", ""),
            "target_audience_label": case.get("target_audience_label", ""),
            "model_id": case["recommendation"]["model_id"],
            "model_name": case["recommendation"]["model_name"],
            "scores": validated["scores"],
            "overall_comment": validated["overall_comment"],
            "risk_flags": validated["risk_flags"],
            "trace_id": getattr(client, "last_trace_id", ""),
        })

    return summarize_results(cases, results, invalid_cases)


def summarize_results(
    cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    invalid_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    totals: dict[str, list[int]] = defaultdict(list)
    audience_totals: dict[str, list[float]] = defaultdict(list)
    for row in results:
        case_avg = sum(row["scores"].values()) / len(DIMENSIONS)
        audience_totals[str(row.get("target_audience") or "unknown")].append(case_avg)
        for dimension, score in row["scores"].items():
            totals[dimension].append(score)

    averages = {
        dimension: round(sum(scores) / len(scores), 2) if scores else 0.0
        for dimension, scores in totals.items()
    }
    by_audience = {
        audience: {
            "average": round(sum(scores) / len(scores), 2),
            "case_count": len(scores),
        }
        for audience, scores in sorted(audience_totals.items())
    }
    low_score_cases = [
        row for row in results
        if min(row["scores"].values()) <= 2 or sum(row["scores"].values()) / len(DIMENSIONS) < 3.5
    ]
    return {
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dataset": "data/eval/explanation_eval.jsonl",
        "model_source": "demo",
        "case_count": len(cases),
        "judged_count": len(results),
        "invalid_count": len(invalid_cases),
        "dimension_averages": averages,
        "audience_averages": by_audience,
        "overall_average": round(
            sum(sum(row["scores"].values()) / len(DIMENSIONS) for row in results) / len(results),
            2,
        ) if results else 0.0,
        "low_score_count": len(low_score_cases),
        "low_score_cases": low_score_cases,
        "invalid_cases": invalid_cases,
        "results": results,
        "limitations": [
            "LLM-as-Judge is only a development aid and does not replace official evaluation metrics.",
            "The judge is instructed to score only from supplied context.",
            "Scores can be biased by the judge model and should be spot-checked manually.",
            "The standardized human questionnaire is designed separately and still requires real respondents.",
        ],
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if report.get("status") == "skipped":
        (output_dir / "llm_judge_skipped.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return
    (output_dir / "llm_judge_results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_jsonl(output_dir / "llm_judge_low_score_cases.jsonl", report.get("low_score_cases", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM-as-Judge explanation quality evaluation.")
    parser.add_argument("--limit", type=int, default=30, help="Expanded explanation samples to judge; 0 means all.")
    parser.add_argument("--top-n", type=int, default=1, help="Recommendations per demand to judge.")
    parser.add_argument("--output-dir", default=str(REPORT_DIR), help="Report output directory.")
    args = parser.parse_args()

    cases = build_cases(limit=args.limit, top_n=args.top_n)
    report = judge_cases(cases)
    write_report(report, Path(args.output_dir))

    if report.get("status") == "skipped":
        print(f"SKIP: {report['reason']}; cases prepared={report['case_count']}")
        print(f"Report: {Path(args.output_dir) / 'llm_judge_skipped.json'}")
        return 0

    print(f"Judged {report['judged_count']} / {report['case_count']} explanation cases.")
    print(f"Overall average: {report['overall_average']}")
    print(f"Report: {Path(args.output_dir) / 'llm_judge_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
