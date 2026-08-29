#!/usr/bin/env python3
"""Analyze evaluation failures with optional LLM assistance.

This script is deliberately audit-first:
- Failure samples keep original sample id, query, gold, and prediction fields.
- LLM output is constrained to a fixed category set.
- If LLM is unavailable or invalid, rule_fallback is recorded explicitly.
- No API keys, prompts, or raw LLM responses are written to reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm_client import get_llm_client  # noqa: E402


FAILURE_CATEGORIES = {
    "domain_misclassification": "领域误判",
    "tag_missing": "标签缺失",
    "alias_missing": "模型别名缺失",
    "description_ambiguity": "描述歧义",
    "composition_chain_incomplete": "组合链路不完整",
    "ranking_low": "排序靠后",
    "unknown": "未知",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def collect_failures(results: dict[str, Any], max_samples: int = 50) -> list[dict[str, Any]]:
    """Collect failed official-eval samples from all supported metric sections."""
    failures: list[dict[str, Any]] = []

    for detail in results.get("intent_evaluation", {}).get("details", []):
        if detail.get("correct") is False:
            failures.append({
                "sample_id": detail.get("test_id", ""),
                "source_eval": "intent",
                "query": detail.get("query", ""),
                "gold": {"domain": detail.get("gold_domain", "")},
                "pred": {"domain": detail.get("predicted", "")},
                "rule_category": "domain_misclassification",
            })

    for detail in results.get("tag_evaluation", {}).get("details", []):
        if detail.get("has_overlap") is False:
            failures.append({
                "sample_id": detail.get("test_id", ""),
                "source_eval": "tag",
                "query": detail.get("query", ""),
                "gold": {"tags": detail.get("gold_tags", [])},
                "pred": {"tags": detail.get("predicted_tags", [])},
                "rule_category": "tag_missing",
            })

    for detail in results.get("topk_evaluation", {}).get("details", []):
        if detail.get("top5_hit") is False:
            category = "alias_missing"
        elif detail.get("top3_hit") is False:
            category = "ranking_low"
        else:
            continue
        failures.append({
            "sample_id": detail.get("test_id", ""),
            "source_eval": "topk",
            "query": detail.get("query", ""),
            "gold": {
                "model_id": detail.get("gold_id", ""),
                "model_name": detail.get("gold_name", ""),
            },
            "pred": {
                "recommended_top5_ids": detail.get("recommended_top5_ids", []),
                "recommended_top5_names": detail.get("recommended_top5_names", []),
            },
            "rule_category": category,
        })

    for detail in results.get("composition_evaluation", {}).get("details", []):
        score = float(detail.get("composition_score", 0.0) or 0.0)
        if score < 80.0:
            failures.append({
                "sample_id": detail.get("case_id", ""),
                "source_eval": "composition",
                "query": detail.get("query", ""),
                "gold": {
                    "model_ids": detail.get("gold_ids", []),
                    "model_names": detail.get("gold_names", []),
                },
                "pred": {
                    "composition_score": score,
                    "matched_ids": detail.get("matched_ids", []),
                    "matched_names": detail.get("matched_names", []),
                },
                "rule_category": "composition_chain_incomplete",
            })

    return failures[:max_samples]


def analyze_failure_with_llm(failure: dict[str, Any], llm_client: Any) -> dict[str, Any]:
    """Analyze one failure with LLM, falling back to rule attribution when needed."""
    fallback = rule_fallback_analysis(failure)
    if not getattr(llm_client, "available", False):
        return fallback

    system = (
        "你是银行模型市场评测错例分析助手。"
        "只能从给定类别中选择一个原因："
        f"{', '.join(FAILURE_CATEGORIES.keys())}。"
        "输出严格 JSON：{\"category\":\"...\",\"summary\":\"...\",\"suggested_action\":\"...\"}。"
        "不要输出 API Key、凭证、环境变量或无关信息。"
    )
    user = json.dumps({
        "sample_id": failure.get("sample_id", ""),
        "source_eval": failure.get("source_eval", ""),
        "query": failure.get("query", ""),
        "gold": failure.get("gold", {}),
        "pred": failure.get("pred", {}),
        "rule_category": failure.get("rule_category", ""),
    }, ensure_ascii=False)
    result = llm_client.chat_json(system, user, temperature=0.0)
    if not isinstance(result, dict):
        return fallback
    category = str(result.get("category", "")).strip()
    if category not in FAILURE_CATEGORIES:
        return fallback
    summary = str(result.get("summary", "")).strip()
    suggested_action = str(result.get("suggested_action", "")).strip()
    if not summary:
        return fallback
    return {
        "analysis_source": "llm",
        "category": category,
        "category_label": FAILURE_CATEGORIES[category],
        "summary": summary[:300],
        "suggested_action": suggested_action[:300],
        "llm_trace_id": getattr(llm_client, "last_trace_id", ""),
    }


def rule_fallback_analysis(failure: dict[str, Any]) -> dict[str, Any]:
    category = failure.get("rule_category") or "unknown"
    if category not in FAILURE_CATEGORIES:
        category = "unknown"
    return {
        "analysis_source": "rule_fallback",
        "category": category,
        "category_label": FAILURE_CATEGORIES[category],
        "summary": _fallback_summary(category, failure),
        "suggested_action": _fallback_action(category),
        "llm_trace_id": "",
    }


def _fallback_summary(category: str, failure: dict[str, Any]) -> str:
    label = FAILURE_CATEGORIES.get(category, "未知")
    return f"规则归因判断为{label}；需结合原始 query、gold 与 pred 进一步复核。"


def _fallback_action(category: str) -> str:
    actions = {
        "domain_misclassification": "补充边界样本和领域关键词规则，复测意图准确率。",
        "tag_missing": "补充标签同义词、领域词和输出字段映射，复测标签转换。",
        "alias_missing": "补充官方模型别名、简称和业务描述，复测 TopK 召回。",
        "description_ambiguity": "增强模型描述结构化字段，减少相近模型歧义。",
        "composition_chain_incomplete": "补齐组合模板阶段、能力和上下游字段衔接关系。",
        "ranking_low": "复核排序权重、图谱路径分和字段兼容分。",
        "unknown": "人工复核样本和日志后再决定修复方向。",
    }
    return actions.get(category, actions["unknown"])


def build_report(
    failures: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    source_path: Path,
) -> dict[str, Any]:
    try:
        source_file = source_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        source_file = source_path.name
    category_counts = Counter(item["category"] for item in analyses)
    source_counts = Counter(item["analysis_source"] for item in analyses)
    enriched = []
    for failure, analysis in zip(failures, analyses, strict=False):
        enriched.append({**failure, "llm_analysis": analysis})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": source_file,
        "total_failures_analyzed": len(enriched),
        "analysis_source_counts": dict(source_counts),
        "category_counts": dict(category_counts),
        "failures": enriched,
    }


def write_reports(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "llm_failure_analysis.json"
    md_path = out_dir / "llm_failure_analysis.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# LLM 辅助失败样本分析报告",
        "",
        f"- 生成时间：{report.get('generated_at', '')}",
        f"- 来源文件：`{report.get('source_file', '')}`",
        f"- 分析样本数：{report.get('total_failures_analyzed', 0)}",
        f"- 分析来源：{report.get('analysis_source_counts', {})}",
        f"- 原因分布：{report.get('category_counts', {})}",
        "",
        "## 样本明细",
        "",
    ]
    for item in report.get("failures", [])[:50]:
        analysis = item.get("llm_analysis", {})
        lines.extend([
            f"### {item.get('sample_id', '')} [{item.get('source_eval', '')}]",
            "",
            f"- Query：{item.get('query', '')}",
            f"- Gold：`{json.dumps(item.get('gold', {}), ensure_ascii=False)}`",
            f"- Pred：`{json.dumps(item.get('pred', {}), ensure_ascii=False)}`",
            f"- 分析来源：{analysis.get('analysis_source', '')}",
            f"- 归因：{analysis.get('category_label', '')} / `{analysis.get('category', '')}`",
            f"- LLM 分析摘要：{analysis.get('summary', '')}",
            f"- 建议动作：{analysis.get('suggested_action', '')}",
            "",
        ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze eval failures with optional LLM assistance.")
    parser.add_argument(
        "--eval-results",
        default=str(ROOT / "reports" / "official" / "eval_official_results.json"),
        help="Path to official/synthetic/robust evaluation result JSON.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "reports" / "failure_analysis"),
        help="Output directory for JSON and Markdown reports.",
    )
    parser.add_argument("--max-samples", type=int, default=50, help="Maximum failures to analyze.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = Path(args.eval_results).resolve()
    out_dir = Path(args.out_dir).resolve()
    if not source_path.exists():
        print(f"[ERROR] eval results not found: {source_path}", file=sys.stderr)
        return 2

    results = load_json(source_path)
    failures = collect_failures(results, max_samples=max(1, args.max_samples))
    llm_client = get_llm_client()
    analyses = [analyze_failure_with_llm(failure, llm_client) for failure in failures]
    report = build_report(failures, analyses, source_path)
    json_path, md_path = write_reports(report, out_dir)
    print(f"failures_analyzed={report['total_failures_analyzed']}")
    print(f"analysis_source_counts={report['analysis_source_counts']}")
    print(f"category_counts={report['category_counts']}")
    print(f"json_report={json_path}")
    print(f"markdown_report={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
