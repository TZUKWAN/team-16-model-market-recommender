#!/usr/bin/env python3
"""
analyze_eval_failures.py - 评测失败归因脚本

Analyzes eval_results.json and topk_failures.json to produce:
  - Console summary
  - failure_summary.md (full markdown report)
  - metrics_summary.json (structured metrics)

Usage:
    python scripts/analyze_eval_failures.py
    python scripts/analyze_eval_failures.py --eval-results path/to/eval_results.json
    python scripts/analyze_eval_failures.py --topk-failures path/to/topk_failures.json
    python scripts/analyze_eval_failures.py --out-dir path/to/output
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

# ---- Constants ----

DOMAIN_PREFIX_MAP = {
    'RISK': 'credit_risk',
    'MKT': 'customer_marketing',
    'OPS': 'operation_management',
}

CATEGORY_LABELS = {
    'intent_mismatch': '意图分类错误',
    'tag_missing_or_weak': '标签缺失或不足',
    'gold_not_recalled': 'Gold模型未被召回',
    'recalled_but_ranked_low': 'Gold被召回但排名过低',
    'cross_domain_confusion': '跨领域混淆',
    'possible_metadata_gap': '可能的元数据缺口',
    'unknown': '未知',
}

CATEGORY_SUGGESTIONS = {
    'intent_mismatch': (
        '优化意图分类模型，增加边界样本训练数据，'
        '细化领域关键词库，提升意图识别的准确性。'
    ),
    'tag_missing_or_weak': (
        '丰富标签体系，增加同义词映射，'
        '优化标签提取算法，确保至少覆盖3个以上关键标签。'
    ),
    'gold_not_recalled': (
        '改进召回机制，扩大候选集覆盖率，'
        '优化特征匹配权重，确保相关模型能被正确触发。'
    ),
    'recalled_but_ranked_low': (
        '优化排序/评分模型，调整评分权重，'
        '增加相关性特征，提升Gold模型在Top3中的占比。'
    ),
    'cross_domain_confusion': (
        '明确领域边界定义，增加领域判别特征，'
        '优化领域分类逻辑，减少跨域混淆。'
    ),
    'possible_metadata_gap': (
        '补充模型元数据描述，扩展知识库覆盖范围，'
        '增加模型标签关键词，提升检索匹配效果。'
    ),
}


# ---- Utility Functions ----


def load_json(path):
    """Safely load a JSON file, return None on error."""
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError) as e:
        print(f"  [WARN] Could not load {path}: {e}", file=sys.stderr)
        return None


def _ensure_list(value):
    """Normalize various input formats to a deduplicated list of strings.

    Handles:
      - list: returns normalized copy
      - None / empty str / whitespace: returns []
      - space/comma/Chinese-punctuation-separated: splits and returns
      - JSON array string: parses and returns
      - single string: returns [value]
    """
    if value is None:
        return []
    if isinstance(value, list):
        result = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                result.append(s)
        return _dedupe_ordered(result)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        # JSON array string like '["a", "b"]'
        if text.startswith('[') and text.endswith(']'):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return _ensure_list(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        # Split by spaces, commas, Chinese commas/ideographic comma/semicolon
        parts = re.split(r'[,\s，、；;]+', text)
        result = [p.strip() for p in parts if p.strip()]
        return _dedupe_ordered(result)
    # Other types: stringify
    s = str(value).strip()
    return [s] if s else []


def _dedupe_ordered(items):
    """Remove duplicates while preserving first-occurrence order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def get_domain_from_id(model_id):
    """Extract domain name from model ID prefix (RISK/MKT/OPS)."""
    if not isinstance(model_id, str) or '_' not in model_id:
        return None
    prefix = model_id.split('_')[0]
    return DOMAIN_PREFIX_MAP.get(prefix)


def capitalize_label(key):
    """Convert snake_case key to readable label."""
    return key.replace('_', ' ').title()


# ---- Classification Logic ----


def classify_failure(entry):
    """Classify a single failure entry into an attribution category.

    Priority order (first match wins):
    1. cross_domain_confusion
    2. gold_not_recalled
    3. recalled_but_ranked_low
    4. tag_missing_or_weak
    5. intent_mismatch
    6. possible_metadata_gap (default)
    """
    gold_ids = _ensure_list(entry.get('gold_ids', []))
    recommended_top5 = _ensure_list(entry.get('recommended_top5', []))
    parsed_tags = entry.get('parsed_tags', []) or []
    parsed_intent = entry.get('parsed_intent', '')

    # Get domains from gold_ids
    gold_domains = [get_domain_from_id(g) for g in gold_ids if get_domain_from_id(g)]

    # Rule 1: cross_domain_confusion
    # ALL gold_ids belong to domains different from parsed_intent
    if gold_domains and parsed_intent:
        if all(d != parsed_intent for d in gold_domains):
            return 'cross_domain_confusion'

    # Rule 2: gold_not_recalled
    if gold_ids and recommended_top5:
        if not any(g in recommended_top5 for g in gold_ids):
            return 'gold_not_recalled'

    # Rule 3: recalled_but_ranked_low
    if gold_ids and len(recommended_top5) >= 3:
        top5_set = set(recommended_top5)
        top3_set = set(recommended_top5[:3])
        if any(g in top5_set for g in gold_ids) and not any(g in top3_set for g in gold_ids):
            return 'recalled_but_ranked_low'

    # Rule 4: tag_missing_or_weak
    if not parsed_tags or len(parsed_tags) < 3:
        return 'tag_missing_or_weak'

    # Rule 5: intent_mismatch
    # parsed_intent matches some gold domains but not all (partial mismatch)
    if gold_domains and parsed_intent:
        matches_intent = sum(1 for d in gold_domains if d == parsed_intent)
        if 0 < matches_intent < len(gold_domains):
            return 'intent_mismatch'

    # Rule 6: possible_metadata_gap (fallback)
    return 'possible_metadata_gap'


# ---- Metrics Extraction ----


def extract_metrics(eval_results):
    """Extract key metrics from eval_results.json, returning None for missing values."""
    metrics = {
        'intent_accuracy_pct': None,
        'tag_precision': None,
        'tag_recall': None,
        'tag_f1': None,
        'top3_hit_rate_pct': None,
        'top5_hit_rate_pct': None,
        'explanation_comprehensibility_pct': None,
        'composition_avg_score': None,
    }

    if eval_results is None:
        return metrics

    # Intent evaluation
    intent_eval = eval_results.get('intent_evaluation')
    if isinstance(intent_eval, dict):
        metrics['intent_accuracy_pct'] = intent_eval.get('accuracy_pct')

    # Tag evaluation
    tag_eval = eval_results.get('tag_evaluation')
    if isinstance(tag_eval, dict):
        metrics['tag_precision'] = tag_eval.get('avg_precision')
        metrics['tag_recall'] = tag_eval.get('avg_recall')
        metrics['tag_f1'] = tag_eval.get('avg_f1')

    # TopK evaluation
    topk_eval = eval_results.get('topk_evaluation')
    if isinstance(topk_eval, dict):
        metrics['top3_hit_rate_pct'] = topk_eval.get('top3_hit_rate_pct')
        metrics['top5_hit_rate_pct'] = topk_eval.get('top5_hit_rate_pct')

    # Explanation evaluation
    expl_eval = eval_results.get('explanation_evaluation')
    if isinstance(expl_eval, dict):
        metrics['explanation_comprehensibility_pct'] = expl_eval.get('overall_rate_pct')

    # Composition evaluation
    comp_eval = eval_results.get('composition_evaluation')
    if isinstance(comp_eval, dict):
        metrics['composition_avg_score'] = comp_eval.get('avg_score')

    return metrics


# ---- Report Generation ----


def generate_failure_summary(metrics, failures, attributions, domain_counts, source_files):
    """Generate the full failure_summary.md markdown report."""
    lines = []
    lines.append('# 评测失败归因分析报告')
    lines.append('')
    lines.append(
        f'生成时间：{datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")}'
    )
    lines.append('')
    lines.append(f'- 数据来源：`{source_files.get("eval_results", "N/A")}`')
    lines.append(f'- 失败数据：`{source_files.get("topk_failures", "N/A")}`')
    lines.append('')

    # ---- 1. 总体指标 ----
    lines.append('## 1. 总体指标')
    lines.append('')
    lines.append('| 指标 | 值 |')
    lines.append('|------|-----|')
    lines.append(
        f'| 意图分类准确率 (Intent Accuracy) | '
        f'{_fmt_pct(metrics["intent_accuracy_pct"])} |'
    )
    lines.append(
        f'| 标签提取精确率 (Tag Precision) | '
        f'{_fmt_val(metrics["tag_precision"])} |'
    )
    lines.append(
        f'| 标签提取召回率 (Tag Recall) | '
        f'{_fmt_val(metrics["tag_recall"])} |'
    )
    lines.append(
        f'| 标签提取 F1 (Tag F1) | '
        f'{_fmt_val(metrics["tag_f1"])} |'
    )
    lines.append(
        f'| Top3 命中率 (Top3 Hit Rate) | '
        f'{_fmt_pct(metrics["top3_hit_rate_pct"])} |'
    )
    lines.append(
        f'| Top5 命中率 (Top5 Hit Rate) | '
        f'{_fmt_pct(metrics["top5_hit_rate_pct"])} |'
    )
    lines.append(
        f'| 解释可理解率 (Explanation Comprehensibility) | '
        f'{_fmt_pct(metrics["explanation_comprehensibility_pct"])} |'
    )
    lines.append(
        f'| 组合编排平均分 (Composition Avg Score) | '
        f'{_fmt_val(metrics["composition_avg_score"])} |'
    )
    lines.append('')

    # ---- 2. TopK 失败归因 ----
    lines.append('## 2. TopK 失败归因')
    lines.append('')
    total_failures = len(failures)
    lines.append(f'分析失败样本总数：**{total_failures}**')
    lines.append('')
    lines.append('| 归因类别 | 数量 | 占比 |')
    lines.append('|----------|------|------|')
    for cat in [
        'intent_mismatch', 'tag_missing_or_weak', 'gold_not_recalled',
        'recalled_but_ranked_low', 'cross_domain_confusion',
        'possible_metadata_gap', 'unknown',
    ]:
        count = attributions.get(cat, 0)
        if count > 0 or cat == 'unknown':
            pct = f'{count / total_failures * 100:.1f}%' if total_failures > 0 else '0.0%'
            label = CATEGORY_LABELS.get(cat, cat)
            lines.append(f'| {label} | {count} | {pct} |')
    lines.append('')

    # ---- 3. 按 Domain 聚合 ----
    lines.append('## 3. 按 Domain 聚合')
    lines.append('')
    lines.append('| 领域 | 失败数量 | 占比 |')
    lines.append('|------|----------|------|')
    for domain in sorted(domain_counts.keys()):
        count = domain_counts[domain]
        pct = f'{count / total_failures * 100:.1f}%' if total_failures > 0 else '0.0%'
        domain_label = capitalize_label(domain)
        lines.append(f'| {domain_label} | {count} | {pct} |')
    lines.append('')

    # ---- 4. 典型失败样本 ----
    lines.append('## 4. 典型失败样本')
    lines.append('')
    MAX_SAMPLES = 20
    samples = failures[:MAX_SAMPLES]
    for i, entry in enumerate(samples, 1):
        query = entry.get('query', '')[:80]
        parsed_intent = entry.get('parsed_intent', 'N/A')
        gold_ids = _ensure_list(entry.get('gold_ids', []))
        recommended_top5 = _ensure_list(entry.get('recommended_top5', []))
        attribution_key = entry.get('_attribution', 'unknown')
        attribution_label = CATEGORY_LABELS.get(attribution_key, attribution_key)

        lines.append(f'### 样本 {i}')
        lines.append('')
        lines.append(f'- **查询**：{query}')
        lines.append(f'- **解析意图**：{parsed_intent}')
        lines.append(f'- **Gold IDs**：{", ".join(gold_ids) if gold_ids else "N/A"}')
        lines.append(
            f'- **推荐 Top5**：{", ".join(recommended_top5) if recommended_top5 else "N/A"}'
        )
        lines.append(f'- **归因类别**：{attribution_label}')
        lines.append('')

    # ---- 5. 后续优化建议 ----
    lines.append('## 5. 后续优化建议')
    lines.append('')
    suggestions_given = False
    for cat in [
        'intent_mismatch', 'tag_missing_or_weak', 'gold_not_recalled',
        'recalled_but_ranked_low', 'cross_domain_confusion',
        'possible_metadata_gap',
    ]:
        count = attributions.get(cat, 0)
        if count > 0:
            suggestions_given = True
            label = CATEGORY_LABELS.get(cat, cat)
            suggestion = CATEGORY_SUGGESTIONS.get(cat, '')
            lines.append(f'- **{label}**（{count} 例）：{suggestion}')
    if not suggestions_given:
        lines.append('（无显著归因类别，暂无需优化建议）')
    lines.append('')

    return '\n'.join(lines)


def generate_metrics_json(metrics, attributions, domain_counts, source_files, total_failures):
    """Generate structured metrics_summary.json."""
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'source_files': source_files,
        'metrics': metrics,
        'failure_attribution': {
            'total_failures': total_failures,
            'categories': dict(attributions),
        },
        'domain_breakdown': {
            domain: {
                'failed': count,
            }
            for domain, count in sorted(domain_counts.items())
        },
    }


def _fmt_pct(value):
    """Format a percentage value for display."""
    if value is None:
        return 'N/A'
    return f'{value:.2f}%'


def _fmt_val(value):
    """Format a numeric value for display."""
    if value is None:
        return 'N/A'
    if isinstance(value, float):
        return f'{value:.4f}'
    return str(value)


# ---- Console Print ----


def print_summary(metrics, failures, attributions, domain_counts):
    """Print a clean console summary."""
    print()
    print('=' * 60)
    print('  评测失败归因分析')
    print('=' * 60)
    print()

    total_failures = len(failures)
    print(f'  分析失败样本总数: {total_failures}')
    print()

    if total_failures > 0:
        print('  Top 归因类别:')
        for cat, count in attributions.most_common(5):
            pct = count / total_failures * 100
            label = CATEGORY_LABELS.get(cat, cat)
            print(f'    {label}: {count} ({pct:.1f}%)')
        print()

    print('  关键指标:')
    has_metrics = any(v is not None for v in metrics.values())
    if has_metrics:
        print(f'    Intent Accuracy: {_fmt_pct(metrics["intent_accuracy_pct"])}')
        print(f'    Tag F1:          {_fmt_val(metrics["tag_f1"])}')
        print(f'    Top3 Hit Rate:   {_fmt_pct(metrics["top3_hit_rate_pct"])}')
        print(f'    Top5 Hit Rate:   {_fmt_pct(metrics["top5_hit_rate_pct"])}')
        print(f'    Explanation:     {_fmt_pct(metrics["explanation_comprehensibility_pct"])}')
        print(f'    Composition:     {_fmt_val(metrics["composition_avg_score"])}')
    else:
        print('    (eval_results.json 未提供)')
    print()


# ---- Argument Parsing ----


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='评测失败归因分析脚本 — 分析 TopK 推荐失败原因',
    )
    parser.add_argument(
        '--eval-results',
        type=str,
        default=None,
        help='Path to eval_results.json (default: reports/examples/eval_results.json)',
    )
    parser.add_argument(
        '--topk-failures',
        type=str,
        default=None,
        help='Path to topk_failures.json (default: reports/examples/topk_failures.json)',
    )
    parser.add_argument(
        '--out-dir',
        type=str,
        default=None,
        help='Output directory (default: reports/analysis)',
    )
    return parser.parse_args(argv)


# ---- Main ----


def main():
    # Fix console encoding for Windows (Chinese characters)
    if sys.stdout.encoding.lower() in ('gbk', 'gb2312', 'cp936'):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[union-attr]

    args = parse_args()

    # Resolve paths relative to project root
    base_dir = Path(__file__).resolve().parent.parent

    eval_results_path = Path(args.eval_results) if args.eval_results else (
        base_dir / 'reports' / 'examples' / 'eval_results.json'
    )
    topk_failures_path = Path(args.topk_failures) if args.topk_failures else (
        base_dir / 'reports' / 'examples' / 'topk_failures.json'
    )
    out_dir = Path(args.out_dir) if args.out_dir else (
        base_dir / 'reports' / 'analysis'
    )

    # Use absolute paths for display
    eval_results_path = eval_results_path.resolve()
    topk_failures_path = topk_failures_path.resolve()
    out_dir = out_dir.resolve()

    print(f'  分析脚本启动...')
    print(f'  Eval results: {eval_results_path}')
    print(f'  TopK failures: {topk_failures_path}')
    print(f'  Output dir: {out_dir}')

    source_files = {
        'eval_results': str(eval_results_path),
        'topk_failures': str(topk_failures_path),
    }

    # Load data
    eval_results = load_json(eval_results_path)
    if eval_results is None and eval_results_path.exists():
        print(f'  [ERROR] Failed to parse {eval_results_path}', file=sys.stderr)
    elif eval_results is None:
        print(f'  [WARN] eval_results.json not found at {eval_results_path}', file=sys.stderr)
        print('  [WARN] All metrics will be set to N/A. Continuing...', file=sys.stderr)

    failures = load_json(topk_failures_path)
    if failures is None and topk_failures_path.exists():
        print(f'  [ERROR] Failed to parse {topk_failures_path}', file=sys.stderr)
        failures = []
    elif failures is None:
        print(f'  [WARN] topk_failures.json not found at {topk_failures_path}', file=sys.stderr)
        print('  [WARN] No failure data to analyze. Generating minimal report.', file=sys.stderr)
        failures = []

    # Validate failures is list
    if not isinstance(failures, list):
        print(f'  [WARN] topk_failures.json is not a list. Got {type(failures).__name__}.', file=sys.stderr)
        failures = []

    # Extract metrics
    metrics = extract_metrics(eval_results)

    # Classify failures
    attributions_list = []
    domain_counts = Counter()
    for entry in failures:
        if not isinstance(entry, dict):
            continue
        try:
            category = classify_failure(entry)
        except Exception as e:
            print(f'  [WARN] Error classifying entry: {e}', file=sys.stderr)
            category = 'unknown'
        entry['_attribution'] = category
        attributions_list.append(category)

        # Domain aggregation
        parsed_intent = entry.get('parsed_intent', '')
        if parsed_intent:
            domain_counts[parsed_intent] += 1

    attributions_counter = Counter(attributions_list)

    # Print console summary
    print_summary(metrics, failures, attributions_counter, domain_counts)

    # Create output directory
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate failure_summary.md
    md_content = generate_failure_summary(
        metrics, failures, attributions_counter, domain_counts, source_files,
    )
    md_path = out_dir / 'failure_summary.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f'  Report saved to: {md_path}')

    # Generate metrics_summary.json
    json_content = generate_metrics_json(
        metrics, attributions_counter, domain_counts, source_files, len(failures),
    )
    json_path = out_dir / 'metrics_summary.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_content, f, ensure_ascii=False, indent=2)
    print(f'  Metrics saved to: {json_path}')

    print()
    print(f'  Done! {len(failures)} failures analyzed.')
    print()

    sys.exit(0)


if __name__ == '__main__':
    main()
