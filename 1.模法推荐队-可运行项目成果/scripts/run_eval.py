#!/usr/bin/env python
"""
run_eval.py - Evaluation script for the Model Market Assistant.

Measures:
- Intent identification accuracy
- Tag precision/recall/F1
- Top-K hit rate (Top3, Top5)
- Composition average fit score
- Explanation comprehensibility

Usage:
    python scripts/run_eval.py --all
    python scripts/run_eval.py --intent
    python scripts/run_eval.py --tag
    python scripts/run_eval.py --topk
    python scripts/run_eval.py --composition
    python scripts/run_eval.py --explanation
"""

from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

# Load .env if available so LLM keys are picked up during evaluation
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:
    pass

from app.services.composition_planner import CompositionPlanner
from app.services.data_loader import get_tag_key_to_name, load_eval_sets, load_tags
from app.services.demand_parser import DemandParser
from app.services.llm_client import get_llm_client
from app.services.recommender import ModelRecommendationService

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('eval')


def eval_intent(parser: DemandParser) -> dict[str, Any]:
    """Evaluate intent identification accuracy."""
    eval_sets = load_eval_sets()
    samples = eval_sets.get('intent_eval', [])
    if not samples:
        samples = [
            {'demand_id': 'd1', 'raw_text': '筛选县域新客做首贷营销', 'gold_intent': 'customer_marketing'},
            {'demand_id': 'd2', 'raw_text': '农户小额贷款贷前准入风控', 'gold_intent': 'credit_risk'},
            {'demand_id': 'd3', 'raw_text': '对公贷款贷后逾期预警', 'gold_intent': 'credit_risk'},
            {'demand_id': 'd4', 'raw_text': '网点客流预测', 'gold_intent': 'operation_management'},
            {'demand_id': 'd5', 'raw_text': '客户流失预警', 'gold_intent': 'customer_marketing'},
        ]

    correct = 0
    details = []
    for s in samples:
        raw = s.get('query', s.get('raw_text', ''))
        gold = s.get('expected_domain', s.get('gold_intent', ''))
        if not raw or not gold:
            continue
        result = parser.parse(raw)
        pred = result.intent
        is_correct = pred == gold
        if is_correct:
            correct += 1
        details.append({
            'demand_id': s.get('demand_id', ''),
            'raw_text': raw[:50],
            'gold': gold,
            'predicted': pred,
            'confidence': result.intent_confidence,
            'correct': is_correct,
        })

    total = len(samples)
    accuracy = round(correct / total * 100, 2) if total > 0 else 0
    return {
        'metric': 'intent_accuracy',
        'total': total,
        'correct': correct,
        'accuracy_pct': accuracy,
        'details': details,
    }


def eval_tag(parser: DemandParser) -> dict[str, Any]:
    """Evaluate tag extraction precision/recall/F1."""
    eval_sets = load_eval_sets()
    samples = eval_sets.get('tag_eval', [])
    if not samples:
        samples = [
            {'demand_id': 't1', 'raw_text': '县域新客首贷营销', 'gold_tags': ['新客', '首贷', '营销转化', '响应预测']},
            {'demand_id': 't2', 'raw_text': '农户小额贷款贷前反欺诈', 'gold_tags': ['农户', '小额贷款', '反欺诈', '涉农贷款']},
        ]

    total_precision = 0.0
    total_recall = 0.0
    total_f1 = 0.0
    details = []

    tags_data = load_tags()
    key_to_name = get_tag_key_to_name(tags_data)
    name_to_key = {v: k for k, v in key_to_name.items()}

    def normalize_eval_tag(t: str) -> str:
        """Normalize a tag value to standard key for comparison."""
        t = str(t).strip()
        if t in key_to_name:
            return t
        if t in name_to_key:
            return name_to_key[t]
        return t

    for s in samples:
        raw = s.get('query', s.get('raw_text', ''))
        expected_keys = s.get('expected_tags', s.get('gold_tags', []))
        gold_set = set(normalize_eval_tag(k) for k in expected_keys)
        result = parser.parse(raw)
        pred_set = set(normalize_eval_tag(t) for t in result.tags)

        if not gold_set:
            continue

        tp = len(pred_set & gold_set)
        precision = tp / len(pred_set) if pred_set else 0
        recall = tp / len(gold_set) if gold_set else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        total_precision += precision
        total_recall += recall
        total_f1 += f1

        gold_names = [key_to_name.get(t, t) for t in gold_set]
        pred_names = [key_to_name.get(t, t) for t in pred_set]

        details.append({
            'demand_id': s.get('demand_id', ''),
            'raw_text': raw[:50],
            'gold_tags': list(gold_set),
            'gold_tag_names': gold_names,
            'predicted_tags': list(pred_set),
            'predicted_tag_names': pred_names,
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
        })

    n = len(samples)
    return {
        'metric': 'tag_extraction',
        'total': n,
        'avg_precision': round(total_precision / n, 4) if n > 0 else 0,
        'avg_recall': round(total_recall / n, 4) if n > 0 else 0,
        'avg_f1': round(total_f1 / n, 4) if n > 0 else 0,
        'details': details,
    }


def eval_topk(recommender: ModelRecommendationService, parser: DemandParser) -> dict[str, Any]:
    """Evaluate Top-K recommendation hit rate."""
    eval_sets = load_eval_sets()
    samples = eval_sets.get('topk_eval', [])
    if not samples:
        samples = [
            {'demand_id': 'k1', 'query': '筛选县域新客做首贷营销', 'gold_model_ids': ['MKT_001', 'MKT_005', 'MKT_006']},
            {'demand_id': 'k2', 'query': '农户小额贷款贷前准入风控', 'gold_model_ids': ['RISK_001', 'RISK_002', 'RISK_003']},
        ]

    top3_hits = 0
    top5_hits = 0
    total = len(samples)
    details = []

    for s in samples:
        query = s.get('query', '')
        gold_ids = set(s.get('expected_model_ids', s.get('gold_model_ids', [])))
        if not query or not gold_ids:
            continue

        parse_result = parser.parse(query)
        parse_dict = {
            'intent': parse_result.intent,
            'tags': parse_result.tags,
            'business_scenario': parse_result.business_scenario,
            'customer_segment': parse_result.customer_segment,
            'business_stage': parse_result.business_stage,
            'expected_outputs': parse_result.expected_outputs,
            'data_conditions': parse_result.data_conditions,
            'product_type': parse_result.product_type,
            'risk_type': parse_result.risk_type,
            'constraints': parse_result.constraints,
        }

        result = recommender.recommend(parse_dict, top_k=5)
        recommended_ids = [r.model_id for r in result.recommendations]

        top3_ids = recommended_ids[:3]
        hit3 = any(g in top3_ids for g in gold_ids)
        hit5 = any(g in recommended_ids for g in gold_ids)

        if hit3:
            top3_hits += 1
        if hit5:
            top5_hits += 1

        details.append({
            'demand_id': s.get('demand_id', ''),
            'query': query[:80],
            'parsed_intent': parse_result.intent,
            'parsed_tags': parse_result.tags,
            'parsed_scenario': parse_result.business_scenario,
            'parsed_customers': parse_result.customer_segment,
            'parsed_outputs': parse_result.expected_outputs,
            'parsed_data_conditions': parse_result.data_conditions,
            'parsed_product_type': parse_result.product_type,
            'parsed_risk_type': parse_result.risk_type,
            'gold_ids': list(gold_ids),
            'recommended_top5': recommended_ids,
            'top3_hit': hit3,
            'top5_hit': hit5,
        })

    return {
        'metric': 'topk_hit_rate',
        'total': total,
        'top3_hits': top3_hits,
        'top5_hits': top5_hits,
        'top3_hit_rate_pct': round(top3_hits / total * 100, 2) if total > 0 else 0,
        'top5_hit_rate_pct': round(top5_hits / total * 100, 2) if total > 0 else 0,
        'details': details,
    }


def save_topk_failures(topk_result: dict[str, Any]) -> None:
    """Save TopK failure cases for debugging."""
    reports_dir = Path(__file__).resolve().parent.parent / 'reports' / 'examples'
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / 'topk_failures.json'

    failures = [
        d for d in topk_result.get('details', [])
        if not d.get('top5_hit')
    ]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(failures, f, ensure_ascii=False, indent=2)

    print(f"  TopK failures saved to: {output_path}")


def eval_composition(planner: CompositionPlanner, parser: DemandParser) -> dict[str, Any]:
    """Evaluate composition quality."""
    eval_sets = load_eval_sets()
    samples = eval_sets.get('composition_eval', [])
    if not samples:
        samples = [
            {'demand_id': 'c1', 'raw_text': '农户小额贷款贷前准入风控，识别欺诈并给额度建议'},
            {'demand_id': 'c2', 'raw_text': '对公贷款贷后逾期预警'},
            {'demand_id': 'c3', 'raw_text': '县域新客首贷营销转化'},
        ]

    scores = []
    details = []
    for s in samples:
        parse_result = parser.parse(s['raw_text'])
        result = planner.plan(parse_result.model_dump())
        score = result.total_score
        scores.append(score)
        details.append({
            'demand_id': s['demand_id'],
            'raw_text': s['raw_text'][:50],
            'composition_score': score,
            'node_count': len(result.nodes),
            'io_rate': result.io_compatibility.compatibility_rate if result.io_compatibility else 0,
        })

    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    return {
        'metric': 'composition_fit',
        'total': len(samples),
        'avg_score': avg_score,
        'details': details,
    }


def eval_explanation(planner: CompositionPlanner, parser: DemandParser) -> dict[str, Any]:
    """Evaluate explanation comprehensibility with LLM-as-judge."""
    eval_sets = load_eval_sets()
    samples = eval_sets.get('explanation_eval', [])
    if not samples:
        samples = [
            {'demand_id': 'e1', 'raw_text': '帮我筛一批县域新客做首贷营销，最好能给出转化概率高的名单。'},
            {'demand_id': 'e2', 'raw_text': '帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。'},
            {'demand_id': 'e3', 'raw_text': '我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。'},
            {'demand_id': 'e4', 'raw_text': '识别小微企业贷款中的欺诈申请，防止骗贷行为。'},
            {'demand_id': 'e5', 'raw_text': '对存量个人客户做信用卡逾期风险预测。'},
            {'demand_id': 'e6', 'raw_text': '哪些存量客户最可能响应理财产品推荐？'},
            {'demand_id': 'e7', 'raw_text': '帮我找到可能流失的高价值客户，提前做挽留。'},
            {'demand_id': 'e8', 'raw_text': '筛选县域新客中可能成为首贷户的白名单。'},
            {'demand_id': 'e9', 'raw_text': '预测网点近期的客流趋势，合理排班。'},
            {'demand_id': 'e10', 'raw_text': '识别交易流水中的异常行为，防范反洗钱风险。'},
        ]

    llm = get_llm_client()
    scores = {
        'business': {'total': 0, 'count': 0},
        'technical': {'total': 0, 'count': 0},
        'management': {'total': 0, 'count': 0},
    }
    details = []
    judge_system = (
        'You are an unbiased evaluator of business document clarity. '
        'Rate the following explanation on how understandable it is '
        'to a specific audience. Score from 1 (incomprehensible) to 5 (perfectly clear). '
        'Output ONLY: {"score": <int 1-5>, "reason": "<one sentence>"}'
    )

    for i, sample in enumerate(samples):
        query = sample.get('query', sample.get('raw_text', ''))
        if not query:
            continue
        result = parser.parse(query)
        comp = planner.plan(result.model_dump())

        for mode, text, audience in [
            ('business', comp.business_explanation, '银行一线业务人员（非技术背景）'),
            ('technical', comp.technical_explanation, '数据科学或IT技术人员'),
            ('management', comp.management_explanation, '银行管理层人员'),
        ]:
            if not text or len(text) < 5:
                details.append({'query': query[:30], 'mode': mode, 'score': 3, 'reason': 'Explanation too short or missing'})
                scores[mode]['total'] += 3
                scores[mode]['count'] += 1
                continue

            judge_user = (
                f'Target audience: {audience}\n'
                f'Explanation: {text}\n\n'
                f'Is this explanation clear and understandable to the {audience}? Rate 1-5.'
            )

            js = llm.chat_json(judge_system, judge_user)
            score = js.get('score', 3) if js else 3
            reason = js.get('reason', '') if js else 'LLM unavailable'
            scores[mode]['total'] += score
            scores[mode]['count'] += 1
            details.append({'query': query[:40], 'mode': mode, 'score': score, 'reason': reason})

        if (i + 1) % 3 == 0:
            print(f"  {i+1}/{len(samples)} explanation cases evaluated...")

    results = {}
    all_4plus = 0
    all_total = 0
    for mode in ['business', 'technical', 'management']:
        s = scores[mode]
        if s['count'] == 0:
            continue
        avg = s['total'] / s['count']
        understandable = sum(1 for d in details if d['mode'] == mode and d['score'] >= 4)
        rate = understandable / s['count'] * 100
        results[mode] = {'avg_score': round(avg, 2), 'understandable_rate': round(rate, 1), 'samples': s['count']}
        all_4plus += understandable
        all_total += s['count']

    overall_rate = round(all_4plus / all_total * 100, 1) if all_total > 0 else 0
    return {
        'metric': 'explanation_comprehensibility',
        'overall_rate_pct': overall_rate,
        'target': 90,
        'status': 'pass' if overall_rate >= 90 else 'fail',
        'by_mode': results,
        'details': details,
    }


def save_results(results: dict[str, Any]):
    """Save evaluation results — MERGE with existing to avoid overwrites."""
    reports_dir = Path(__file__).resolve().parent.parent / 'reports' / 'examples'
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / 'eval_results.json'

    # Merge with existing results if present
    existing: dict[str, Any] = {}
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            pass

    merged = {**existing, **results}
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Model Market Assistant Evaluation')
    parser.add_argument('--intent', action='store_true', help='Evaluate intent accuracy')
    parser.add_argument('--tag', action='store_true', help='Evaluate tag extraction')
    parser.add_argument('--topk', action='store_true', help='Evaluate Top-K hit rate')
    parser.add_argument('--composition', action='store_true', help='Evaluate composition quality')
    parser.add_argument('--explanation', action='store_true', help='Evaluate explanation comprehensibility')
    parser.add_argument('--all', action='store_true', help='Run all evaluations')
    args = parser.parse_args()

    run_all = args.all or not (args.intent or args.tag or args.topk or args.composition or args.explanation)
    results: dict[str, Any] = {}

    print('=' * 60)
    print('Model Market Assistant - Evaluation Suite')
    print('=' * 60)

    if run_all or args.intent:
        print('\n>>> Intent Evaluation...')
        dp = DemandParser()
        intent_result = eval_intent(dp)
        print(f"  Accuracy: {intent_result['accuracy_pct']}% ({intent_result['correct']}/{intent_result['total']})")
        results['intent_evaluation'] = intent_result

    if run_all or args.tag:
        print('\n>>> Tag Extraction Evaluation...')
        dp = DemandParser()
        tag_result = eval_tag(dp)
        print(f"  Precision: {tag_result['avg_precision']:.4f}")
        print(f"  Recall: {tag_result['avg_recall']:.4f}")
        print(f"  F1: {tag_result['avg_f1']:.4f}")
        results['tag_evaluation'] = tag_result

    if run_all or args.topk:
        print('\n>>> Top-K Evaluation...')
        rec = ModelRecommendationService()
        dp = DemandParser()
        topk_result = eval_topk(rec, dp)
        print(f"  Top3 Hit Rate: {topk_result['top3_hit_rate_pct']}%")
        print(f"  Top5 Hit Rate: {topk_result['top5_hit_rate_pct']}%")
        results['topk_evaluation'] = topk_result
        save_topk_failures(topk_result)

    if run_all or args.composition:
        print('\n>>> Composition Evaluation...')
        plan = CompositionPlanner()
        dp = DemandParser()
        comp_result = eval_composition(plan, dp)
        print(f"  Avg Score: {comp_result['avg_score']}")
        results['composition_evaluation'] = comp_result

    if run_all or args.explanation:
        print('\n>>> Explanation Evaluation...')
        plan = CompositionPlanner()
        dp = DemandParser()
        exp_result = eval_explanation(plan, dp)
        print(f"  Overall Comprehensibility: {exp_result['overall_rate_pct']}%")
        results['explanation_evaluation'] = exp_result

    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    if 'intent_evaluation' in results:
        r = results['intent_evaluation']
        print(f"  Intent Accuracy: {r['accuracy_pct']}%")
    if 'tag_evaluation' in results:
        r = results['tag_evaluation']
        print(f"  Tag F1: {r['avg_f1']:.4f}")
    if 'topk_evaluation' in results:
        r = results['topk_evaluation']
        print(f"  Top3 Hit Rate: {r['top3_hit_rate_pct']}%")
        print(f"  Top5 Hit Rate: {r['top5_hit_rate_pct']}%")
    if 'composition_evaluation' in results:
        r = results['composition_evaluation']
        print(f"  Composition Avg Score: {r['avg_score']}")
    if 'explanation_evaluation' in results:
        r = results['explanation_evaluation']
        print(f"  Explanation Comprehensibility: {r['overall_rate_pct']}%")

    save_results(results)
    print('\nEvaluation complete!')


if __name__ == '__main__':
    main()
