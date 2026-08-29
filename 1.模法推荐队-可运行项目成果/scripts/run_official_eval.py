#!/usr/bin/env python3
"""
run_official_eval.py - Official evaluation script using the official dataset.

Metrics computed:
  - Intent identification accuracy (based on expected_domain, NOT model_name)
  - Tag conversion accuracy (based on expected_tags)
  - Top3 hit rate (based on gold_model_id/gold_model_name, NOT demo model_id)
  - Top5 hit rate (based on gold_model_id/gold_model_name)
  - Composition fitness (based on combo_eval_official_manual, NOT single-model TopK)

Usage:
    python scripts/run_official_eval.py --all
    python scripts/run_official_eval.py --intent
    python scripts/run_official_eval.py --tag
    python scripts/run_official_eval.py --topk
    python scripts/run_official_eval.py --composition
"""

from __future__ import annotations
import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
except Exception:
    pass

from app.services.composition_planner import CompositionPlanner
from app.services.data_loader import get_tag_key_to_name, load_tags
from app.services.demand_parser import DemandParser
from app.services.recommender import ModelRecommendationService

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('official_eval')

BASE_DIR = Path(__file__).resolve().parent.parent
EVAL_DIR = BASE_DIR / "data" / "eval_official"
REPORTS_DIR = BASE_DIR / "reports" / "official"


def load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file."""
    records = []
    if not path.exists():
        return records
    with open(path, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def filter_split(samples: list[dict], split: str = 'all') -> list[dict]:
    """Filter official records by the train/val/test prefix without reshuffling."""
    selected = str(split or 'all').lower()
    if selected == 'all':
        return samples
    prefix = f'{selected}_'
    return [sample for sample in samples if str(sample.get('test_id', '')).startswith(prefix)]


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, or 'missing' if not found."""
    if not path.exists():
        return 'missing'
    digest = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _git_provenance() -> dict[str, Any]:
    """Best-effort git provenance; empty dict when git or the repo is unavailable."""
    git_info: dict[str, Any] = {}
    try:
        for key, args in (
            ('commit_sha', ['rev-parse', 'HEAD']),
            ('branch', ['rev-parse', '--abbrev-ref', 'HEAD']),
            ('short_sha', ['rev-parse', '--short', 'HEAD']),
        ):
            result = subprocess.run(
                ['git', *args],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                git_info[key] = result.stdout.strip()
        dirty = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if dirty.returncode == 0:
            git_info['working_tree_dirty'] = bool(dirty.stdout.strip())
            git_info['dirty_file_count'] = len([ln for ln in dirty.stdout.splitlines() if ln.strip()])
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return git_info


def _env_provenance() -> dict[str, Any]:
    """Explicit host-provided provenance fallback for containers without git access.

    Reads SOURCE_COMMIT / SOURCE_BRANCH / SOURCE_WORKTREE_DIRTY. Returns an empty
    dict unless all three are present, so a partial environment never produces
    half-credible metadata.
    """
    commit = os.getenv('SOURCE_COMMIT', '').strip()
    branch = os.getenv('SOURCE_BRANCH', '').strip()
    dirty = os.getenv('SOURCE_WORKTREE_DIRTY', '').strip().lower()
    if not (commit and branch and dirty in {'true', 'false'}):
        return {}
    return {
        'commit_sha': commit,
        'branch': branch,
        'short_sha': commit[:7],
        'working_tree_dirty': dirty == 'true',
    }


def compute_provenance() -> dict[str, Any]:
    """Compute config/code/asset hashes so a metric report is reproducible and traceable."""
    provenance: dict[str, Any] = {
        'config_hash_sha256': {},
        'asset_hash_sha256': {},
        'code_provenance': {},
    }
    config_paths = [
        BASE_DIR / 'data' / 'config' / 'recommendation_weights.json',
        BASE_DIR / 'data' / 'config',
        BASE_DIR / '.env.example',
    ]
    for path in config_paths:
        if path.is_file():
            provenance['config_hash_sha256'][str(path.relative_to(BASE_DIR))] = _sha256_file(path)
    provenance['asset_hash_sha256']['official_catalog'] = _sha256_file(
        BASE_DIR / 'data' / 'official' / 'model_catalog_structured.jsonl'
    )
    provenance['asset_hash_sha256']['knowledge_nodes'] = _sha256_file(
        BASE_DIR / 'data' / 'knowledge' / 'graph_nodes.jsonl'
    )
    provenance['asset_hash_sha256']['knowledge_edges'] = _sha256_file(
        BASE_DIR / 'data' / 'knowledge' / 'graph_edges.jsonl'
    )
    provenance['asset_hash_sha256']['topk_eval'] = _sha256_file(
        EVAL_DIR / 'topk_eval_official.jsonl'
    )
    # Real git results win; the environment fallback is only for containers that
    # cannot see .git; when neither works the source is marked unknown (never faked).
    git_info = _git_provenance()
    if git_info.get('commit_sha'):
        git_info['provenance_source'] = 'git'
    else:
        env_info = _env_provenance()
        if env_info:
            git_info = env_info
            git_info['provenance_source'] = 'environment_fallback'
        else:
            git_info = {'provenance_source': 'unknown'}
    provenance['code_provenance'] = git_info
    return provenance


def eval_intent(
    parser: DemandParser,
    use_llm: bool | None = None,
    split: str = 'all',
) -> dict[str, Any]:
    """Evaluate intent identification accuracy using expected_domain."""
    samples = filter_split(load_jsonl(EVAL_DIR / "intent_eval_official.jsonl"), split)
    if not samples:
        return {'metric': 'intent_accuracy', 'total': 0, 'correct': 0, 'accuracy_pct': 0.0, 'details': []}

    correct = 0
    details = []
    for s in samples:
        query = s.get('query', '')
        # NOTE: expected_intent is always 'model_recommendation', so we use expected_domain
        gold_domain = s.get('expected_domain', '')
        if not query or not gold_domain:
            continue
        result = parser.parse(query, use_llm=use_llm)
        # The parser returns intent as domain (credit_risk, customer_marketing, operation_management)
        pred = result.intent
        is_correct = pred == gold_domain
        if is_correct:
            correct += 1
        details.append({
            'test_id': s.get('test_id', ''),
            'query': query[:80],
            'gold_domain': gold_domain,
            'predicted': pred,
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


def eval_tag(
    parser: DemandParser,
    use_llm: bool | None = None,
    split: str = 'all',
) -> dict[str, Any]:
    """Evaluate tag extraction accuracy based on expected_tags."""
    samples = filter_split(load_jsonl(EVAL_DIR / "tag_eval_official.jsonl"), split)
    if not samples:
        return {'metric': 'tag_accuracy', 'total': 0, 'correct': 0, 'accuracy_pct': 0.0, 'details': []}

    tags_data = load_tags()
    key_to_name = get_tag_key_to_name(tags_data)
    name_to_key = {v: k for k, v in key_to_name.items()}

    def normalize_tag(t: str) -> str:
        t = str(t).strip()
        if t in name_to_key:
            return name_to_key[t]
        return t

    correct = 0
    details = []
    for s in samples:
        query = s.get('query', '')
        expected_tags = s.get('expected_tags', [])
        if not query or not expected_tags:
            continue
        result = parser.parse(query, use_llm=use_llm)
        pred_tags = set(normalize_tag(t) for t in result.tags)
        gold_tags = set(normalize_tag(t) for t in expected_tags)

        # Tag conversion accuracy: at least one expected tag is predicted
        # Alternative: exact match or overlap-based
        # Using intersection-based accuracy (any overlap = correct for this metric)
        has_overlap = len(pred_tags & gold_tags) > 0
        if has_overlap:
            correct += 1

        details.append({
            'test_id': s.get('test_id', ''),
            'query': query[:80],
            'gold_tags': list(gold_tags),
            'predicted_tags': list(pred_tags),
            'has_overlap': has_overlap,
        })

    total = len(samples)
    accuracy = round(correct / total * 100, 2) if total > 0 else 0
    return {
        'metric': 'tag_accuracy',
        'total': total,
        'correct': correct,
        'accuracy_pct': accuracy,
        'details': details,
    }


def eval_topk(
    recommender: ModelRecommendationService,
    parser: DemandParser,
    use_llm: bool | None = None,
    parser_use_llm: bool | None = None,
    rerank_use_llm: bool | None = None,
    use_keyword_rules: bool | None = None,
    use_hybrid_retrieval: bool | None = None,
    split: str = 'all',
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Evaluate Top-K recommendation hit rate using gold_model_id/gold_model_name.

    ``use_llm`` / ``use_keyword_rules`` are forwarded to ``recommend()`` for
    ablation experiments; when ``None`` the legacy behavior is preserved.
    """
    samples = filter_split(load_jsonl(EVAL_DIR / "topk_eval_official.jsonl"), split)
    if case_ids:
        samples = [sample for sample in samples if str(sample.get('test_id', '')) in case_ids]
    if not samples:
        return {'metric': 'topk_hit_rate', 'total': 0, 'top1_hits': 0, 'top3_hits': 0, 'top5_hits': 0,
                'top1_hit_rate_pct': 0.0, 'top3_hit_rate_pct': 0.0, 'top5_hit_rate_pct': 0.0, 'details': []}

    top1_hits = 0
    top3_hits = 0
    top5_hits = 0
    details = []
    parser_llm_count = 0
    parser_fallback_count = 0
    rerank_attempt_count = 0
    rerank_success_count = 0
    trace_case_count = 0
    trace_ids: set[str] = set()
    dense_requested_case_count = 0
    dense_available_case_count = 0
    retrieval_mode_counts: dict[str, int] = {}
    per_model_counts: dict[str, dict[str, int]] = {}
    per_scenario_counts: dict[str, dict[str, int]] = {}
    parser_mode = use_llm if parser_use_llm is None else parser_use_llm
    rerank_mode = use_llm if rerank_use_llm is None else rerank_use_llm

    for s in samples:
        query = s.get('query', '')
        gold_id = s.get('gold_model_id', '')
        gold_name = s.get('gold_model_name', '')
        if not query or not gold_id:
            continue

        parse_result = parser.parse(query, use_llm=parser_mode)
        if parse_result.parse_source == 'llm':
            parser_llm_count += 1
        if parse_result.parse_source == 'hybrid_fallback':
            parser_fallback_count += 1
        parser_trace = str(getattr(parse_result, 'llm_trace_id', '') or '')
        if parser_trace:
            trace_ids.add(parser_trace)
        parse_dict = parse_result.model_dump()
        parse_dict["model_source"] = "official"

        recommender.last_llm_rerank_audit = {}
        result = recommender.recommend(
            parse_dict,
            top_k=5,
            use_llm=rerank_mode,
            use_llm_reason=False,
            use_keyword_rules=use_keyword_rules,
            use_hybrid_retrieval=use_hybrid_retrieval,
        )
        rerank_audit = dict(recommender.last_llm_rerank_audit)
        retrieval_audit = dict(recommender.last_hybrid_retrieval_audit)
        dense_requested_case_count += int(bool(retrieval_audit.get('dense_requested')))
        dense_available_case_count += int(bool(retrieval_audit.get('dense_available')))
        retrieval_mode = str(retrieval_audit.get('mode') or 'unknown')
        retrieval_mode_counts[retrieval_mode] = retrieval_mode_counts.get(retrieval_mode, 0) + 1
        rerank_attempt_count += int(bool(rerank_audit.get('attempted')))
        rerank_success_count += int(bool(rerank_audit.get('success')))
        case_trace_ids = set(rerank_audit.get('trace_ids') or [])
        if parser_trace:
            case_trace_ids.add(parser_trace)
        trace_ids.update(case_trace_ids)
        trace_case_count += int(bool(case_trace_ids))
        recommended_ids = [r.model_id for r in result.recommendations]
        recommended_names = [r.model_name for r in result.recommendations]

        top3_ids = recommended_ids[:3]
        top3_names = recommended_names[:3]

        # Hit based on gold_model_id OR gold_model_name
        hit1 = (recommended_ids[:1] == [gold_id]) or (recommended_names[:1] == [gold_name])
        hit3 = (gold_id in top3_ids) or (gold_name in top3_names)
        hit5 = (gold_id in recommended_ids) or (gold_name in recommended_names)

        if hit1:
            top1_hits += 1
        if hit3:
            top3_hits += 1
        if hit5:
            top5_hits += 1

        scenario = str(s.get('scenario') or 'unknown')
        for key, groups in ((str(gold_id), per_model_counts), (scenario, per_scenario_counts)):
            bucket = groups.setdefault(key, {'total': 0, 'top1_hits': 0, 'top3_hits': 0, 'top5_hits': 0})
            bucket['total'] += 1
            bucket['top1_hits'] += int(hit1)
            bucket['top3_hits'] += int(hit3)
            bucket['top5_hits'] += int(hit5)
        gold_rank = next(
            (index for index, model_id in enumerate(recommended_ids, start=1) if model_id == gold_id),
            None,
        )

        details.append({
            'test_id': s.get('test_id', ''),
            'query': query,
            'gold_id': gold_id,
            'gold_name': gold_name,
            'recommended_top5_ids': recommended_ids,
            'recommended_top5_names': recommended_names,
            'top1_hit': hit1,
            'top3_hit': hit3,
            'top5_hit': hit5,
            'gold_rank_in_returned_top5': gold_rank,
            'parse_source': parse_result.parse_source,
            'parser_trace_id': parser_trace,
            'rerank_audit': rerank_audit,
            'hybrid_retrieval_audit': retrieval_audit,
        })

    total = len(samples)

    def summarize_groups(groups: dict[str, dict[str, int]]) -> dict[str, dict[str, float | int]]:
        return {
            key: {
                **bucket,
                'top3_hit_rate_pct': round(bucket['top3_hits'] / bucket['total'] * 100, 2),
                'top5_hit_rate_pct': round(bucket['top5_hits'] / bucket['total'] * 100, 2),
            }
            for key, bucket in sorted(groups.items())
        }

    per_model = summarize_groups(per_model_counts)
    per_scenario = summarize_groups(per_scenario_counts)
    macro_top3 = (
        round(sum(row['top3_hit_rate_pct'] for row in per_model.values()) / len(per_model), 2)
        if per_model else 0.0
    )
    macro_top5 = (
        round(sum(row['top5_hit_rate_pct'] for row in per_model.values()) / len(per_model), 2)
        if per_model else 0.0
    )
    return {
        'metric': 'topk_hit_rate',
        'total': total,
        'top1_hits': top1_hits,
        'top3_hits': top3_hits,
        'top5_hits': top5_hits,
        'top1_hit_rate_pct': round(top1_hits / total * 100, 2) if total > 0 else 0,
        'top3_hit_rate_pct': round(top3_hits / total * 100, 2) if total > 0 else 0,
        'top5_hit_rate_pct': round(top5_hits / total * 100, 2) if total > 0 else 0,
        'macro_by_gold_model_top3_pct': macro_top3,
        'macro_by_gold_model_top5_pct': macro_top5,
        'gold_model_coverage_count': len(per_model),
        'per_gold_model': per_model,
        'per_scenario': per_scenario,
        'split': split,
        'pipeline': {
            'use_llm_requested': parser_mode is True or rerank_mode is True,
            'parser_use_llm': parser_mode,
            'rerank_use_llm': rerank_mode,
            'llm_available': bool(parser.llm.available and recommender.llm.available),
            'use_keyword_rules': use_keyword_rules,
            'use_hybrid_retrieval': use_hybrid_retrieval,
            'dense_enabled': bool(recommender.hybrid_config.get('dense_enabled')),
            'dense_weight': float(recommender.hybrid_config.get('dense_weight', 0.0)),
            'dense_model': str(recommender.hybrid_config.get('dense_model') or ''),
        },
        'llm_evidence': {
            'parser_llm_count': parser_llm_count,
            'parser_fallback_count': parser_fallback_count,
            'rerank_attempt_count': rerank_attempt_count,
            'rerank_success_count': rerank_success_count,
            'trace_case_count': trace_case_count,
            'trace_case_coverage_pct': round(trace_case_count / total * 100, 2) if total else 0.0,
            'unique_trace_count': len(trace_ids),
        },
        'retrieval_evidence': {
            'dense_requested_case_count': dense_requested_case_count,
            'dense_available_case_count': dense_available_case_count,
            'dense_case_coverage_pct': (
                round(dense_available_case_count / total * 100, 2) if total else 0.0
            ),
            'retrieval_mode_counts': retrieval_mode_counts,
            'dense_model': str(recommender.hybrid_config.get('dense_model') or ''),
            'dense_weight': float(recommender.hybrid_config.get('dense_weight', 0.0)),
            'dense_runtime': {
                key: recommender.dense_runtime_status().get(key)
                for key in (
                    'retrieval_runtime_mode',
                    'dense_available',
                    'dense_manifest_verified',
                    'dense_embedding_dimension',
                    'dense_expected_revision',
                    'dense_offline',
                )
            },
        },
        'details': details,
    }


def eval_composition(planner: CompositionPlanner, parser: DemandParser, use_llm: bool | None = None) -> dict[str, Any]:
    """Evaluate composition fitness using combo_eval_official_manual."""
    samples = load_jsonl(EVAL_DIR / "combo_eval_official_manual.jsonl")
    if not samples:
        return {'metric': 'composition_fitness', 'total': 0, 'avg_score': 0.0, 'details': []}

    scores = []
    details = []
    for s in samples:
        query = s.get('query', '')
        gold_ids = set(s.get('gold_model_ids', []))
        gold_names = set(s.get('gold_model_names', []))
        if not query:
            continue

        parse_result = parser.parse(query, use_llm=use_llm)
        result = planner.plan(parse_result.model_dump())
        score = result.total_score
        scores.append(score)

        # Also check if any gold models appear in the composition
        node_ids = [n.model_id for n in result.nodes]
        node_names = [n.model_name for n in result.nodes]
        matched_ids = gold_ids & set(node_ids)
        matched_names = gold_names & set(node_names)
        has_match = len(matched_ids) > 0 or len(matched_names) > 0
        io_status_counts = {
            'pass': sum(1 for e in result.flow_edges if e.io_status == 'pass'),
            'partial': sum(1 for e in result.flow_edges if e.io_status == 'partial'),
            'fail': sum(1 for e in result.flow_edges if e.io_status == 'fail'),
        }
        failed_edges = [
            {
                'source_node_id': e.source_node_id,
                'target_node_id': e.target_node_id,
                'missing_fields': e.missing_fields,
                'suggestion': e.suggestion,
            }
            for e in result.flow_edges if e.io_status == 'fail'
        ]
        degraded_edges = [
            {
                'source_node_id': e.source_node_id,
                'target_node_id': e.target_node_id,
                'missing_fields': e.missing_fields,
                'suggestion': e.suggestion,
            }
            for e in result.flow_edges if e.io_status == 'partial'
        ]
        hard_dependency_targets = {e.target_node_id for e in result.flow_edges if e.io_status == 'fail'}
        soft_dependency_targets = {e.target_node_id for e in result.flow_edges if e.io_status == 'partial'}

        details.append({
            'case_id': s.get('case_id', ''),
            'query': query[:80],
            'composition_score': score,
            'composition_name': result.composition_name,
            'composition_status': result.composition_status,
            'failure_reasons': result.failure_reasons,
            'node_model_ids': [n.model_id for n in result.nodes],
            'gold_ids': list(gold_ids),
            'matched_ids': list(matched_ids),
            'matched_names': list(matched_names),
            'has_match': has_match,
            'node_count': len(result.nodes),
            'io_status_counts': io_status_counts,
            'io_compatibility': result.io_compatibility.model_dump(),
            'failed_edges': failed_edges,
            'degraded_edges': degraded_edges,
            'blocked_nodes': [n.node_id for n in result.nodes if n.node_id in hard_dependency_targets],
            'degraded_nodes': [n.node_id for n in result.nodes if n.node_id in soft_dependency_targets],
        })

    avg_score = round(sum(scores) / len(scores), 2) if scores else 0
    return {
        'metric': 'composition_fitness',
        'total': len(samples),
        'avg_score': avg_score,
        'details': details,
    }


def save_results(
    results: dict[str, Any],
    *,
    split: str = 'all',
    output: str = '',
):
    """Save evaluation results to reports/official/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if output:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = BASE_DIR / output_path
    elif split == 'all':
        output_path = REPORTS_DIR / 'eval_official_results.json'
    else:
        output_path = REPORTS_DIR / f'eval_official_{split}_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to: {output_path}")


def should_save_metric_report(results: dict[str, Any], output: str = '') -> bool:
    """Do not let an ablation-only run overwrite the authoritative metric report."""
    metric_keys = {
        'intent_evaluation',
        'tag_evaluation',
        'topk_evaluation',
        'composition_evaluation',
    }
    return bool(output or metric_keys & results.keys())


def main():
    parser = argparse.ArgumentParser(description='Official Dataset Evaluation')
    parser.add_argument('--intent', action='store_true', help='Evaluate intent accuracy')
    parser.add_argument('--tag', action='store_true', help='Evaluate tag accuracy')
    parser.add_argument('--topk', action='store_true', help='Evaluate Top-K hit rate')
    parser.add_argument('--composition', action='store_true', help='Evaluate composition fitness')
    parser.add_argument('--all', action='store_true', help='Run all evaluations')
    parser.add_argument('--ablation', action='store_true',
                        help='Run rule-vs-LLM ablation on TopK (writes reports/ablation/)')
    parser.add_argument('--split', choices=['all', 'train', 'val', 'test'], default='all',
                        help='Evaluate a locked official split (default: all)')
    parser.add_argument('--llm-mode', choices=['off', 'auto', 'on'], default='off',
                        help='LLM execution mode. "on" requests live LLM and records trace evidence.')
    parser.add_argument('--llm-scope', choices=['parser', 'rerank', 'both'], default='rerank',
                        help='Apply LLM mode to parsing, reranking, or both (default: rerank).')
    parser.add_argument('--keyword-rules', choices=['off', 'on'], default='off',
                        help='Enable legacy pair-specific keyword alignment rules.')
    parser.add_argument('--hybrid-retrieval', choices=['off', 'on'], default='on',
                        help='Enable factual model-card hybrid retrieval.')
    parser.add_argument('--dense-retrieval', choices=['config', 'off', 'on'], default='config',
                        help='Override the configured dense embedding retrieval switch.')
    parser.add_argument('--dense-weight', type=float, default=None,
                        help='Override dense share within retrieval fusion (0..1).')
    parser.add_argument('--live-llm-ablation', action='store_true',
                        help='Actually execute the live LLM ablation mode; otherwise it is marked skipped.')
    parser.add_argument('--require-live-llm', action='store_true',
                        help='Fail instead of silently falling back when --llm-mode on is unavailable.')
    parser.add_argument('--output', default='', help='Optional JSON output path.')
    parser.add_argument('--case-ids', default='',
                        help='Optional comma-separated test IDs for a targeted smoke run.')
    args = parser.parse_args()

    if args.dense_weight is not None and not 0 <= args.dense_weight <= 1:
        parser.error('--dense-weight must be between 0 and 1')
    if args.dense_retrieval != 'config':
        os.environ['HYBRID_DENSE_ENABLED'] = str(args.dense_retrieval == 'on').lower()
    if args.dense_weight is not None:
        os.environ['HYBRID_DENSE_WEIGHT'] = str(args.dense_weight)

    run_all = args.all or not (args.intent or args.tag or args.topk or args.composition or args.ablation)
    requested_llm = {'off': False, 'auto': None, 'on': True}[args.llm_mode]
    parser_use_llm = requested_llm if args.llm_scope in {'parser', 'both'} else False
    rerank_use_llm = requested_llm if args.llm_scope in {'rerank', 'both'} else False
    case_ids = {item.strip() for item in args.case_ids.split(',') if item.strip()}
    use_keyword_rules = args.keyword_rules == 'on'
    use_hybrid_retrieval = args.hybrid_retrieval == 'on'
    results: dict[str, Any] = {
        'evaluation_metadata': {
            'generated_at': datetime.now().isoformat(),
            'split': args.split,
            'llm_mode': args.llm_mode,
            'llm_scope': args.llm_scope,
            'keyword_rules': use_keyword_rules,
            'hybrid_retrieval': use_hybrid_retrieval,
            'dense_retrieval_override': args.dense_retrieval,
            'dense_weight_override': args.dense_weight,
            'provenance': compute_provenance(),
            'split_responsibility': {
                'train_count': 291,
                'val_count': 64,
                'test_count': 62,
                'all_count': 417,
                'rule': 'train/val用于选择和校准参数；test冻结后只做最终一次确认，禁止根据test失败继续调参。',
            },
        }
    }

    print('=' * 60)
    print('OFFICIAL DATASET EVALUATION')
    print('=' * 60)

    if run_all or args.intent:
        print('\n>>> Intent Evaluation (official) ...')
        dp = DemandParser()
        if args.require_live_llm and parser_use_llm is True and not dp.llm.available:
            raise SystemExit('Live LLM required but not configured')
        intent_result = eval_intent(dp, use_llm=parser_use_llm, split=args.split)
        print(f"  Accuracy: {intent_result['accuracy_pct']}% ({intent_result['correct']}/{intent_result['total']})")
        results['intent_evaluation'] = intent_result

    if run_all or args.tag:
        print('\n>>> Tag Conversion Evaluation (official) ...')
        dp = DemandParser()
        if args.require_live_llm and parser_use_llm is True and not dp.llm.available:
            raise SystemExit('Live LLM required but not configured')
        tag_result = eval_tag(dp, use_llm=parser_use_llm, split=args.split)
        print(f"  Tag Accuracy: {tag_result['accuracy_pct']}% ({tag_result['correct']}/{tag_result['total']})")
        results['tag_evaluation'] = tag_result

    if run_all or args.topk:
        print('\n>>> Top-K Evaluation (official) ...')
        rec = ModelRecommendationService()
        dp = DemandParser()
        live_missing = (
            (parser_use_llm is True and not dp.llm.available)
            or (rerank_use_llm is True and not rec.llm.available)
        )
        if args.require_live_llm and live_missing:
            raise SystemExit('Live LLM required but not configured')
        topk_result = eval_topk(
            rec,
            dp,
            use_llm=False,
            parser_use_llm=parser_use_llm,
            rerank_use_llm=rerank_use_llm,
            use_keyword_rules=use_keyword_rules,
            use_hybrid_retrieval=use_hybrid_retrieval,
            split=args.split,
            case_ids=case_ids or None,
        )
        print(f"  Top3 Hit Rate: {topk_result['top3_hit_rate_pct']}%")
        print(f"  Top5 Hit Rate: {topk_result['top5_hit_rate_pct']}%")
        print(
            "  Dense Coverage: "
            f"{topk_result['retrieval_evidence']['dense_available_case_count']}/"
            f"{topk_result['total']}"
        )
        results['topk_evaluation'] = topk_result

    if args.ablation:
        print('\n>>> Ablation Evaluation (official topk, rule vs LLM) ...')
        ablation_modes = {
            'legacy_keyword_rule': {
                'use_llm': False,
                'use_keyword_rules': True,
                'use_hybrid_retrieval': False,
            },
            'no_keyword_no_hybrid': {
                'use_llm': False,
                'use_keyword_rules': False,
                'use_hybrid_retrieval': False,
            },
            'hybrid_no_keyword': {
                'use_llm': False,
                'use_keyword_rules': False,
                'use_hybrid_retrieval': True,
            },
        }
        ablation_results: dict[str, Any] = {}
        for mode_name, flags in ablation_modes.items():
            print(f'  - mode: {mode_name}')
            rec = ModelRecommendationService()
            dp = DemandParser()
            r = eval_topk(rec, dp, split=args.split, case_ids=case_ids or None, **flags)
            ablation_results[mode_name] = {
                'top3_hit_rate_pct': r['top3_hit_rate_pct'],
                'top5_hit_rate_pct': r['top5_hit_rate_pct'],
                'top3_hits': r['top3_hits'],
                'top5_hits': r['top5_hits'],
                'total': r['total'],
                'pipeline': r['pipeline'],
                'llm_evidence': r['llm_evidence'],
                'retrieval_evidence': r['retrieval_evidence'],
            }
        if args.live_llm_ablation:
            rec = ModelRecommendationService()
            dp = DemandParser()
            if not (rec.llm.available and dp.llm.available):
                ablation_results['hybrid_live_llm'] = {
                    'status': 'skipped',
                    'reason': 'live_llm_not_configured',
                    'llm_available': False,
                }
                if args.require_live_llm:
                    raise SystemExit('Live LLM ablation required but not configured')
            else:
                print('  - mode: hybrid_live_llm')
                r = eval_topk(
                    rec,
                    dp,
                    split=args.split,
                    use_llm=False,
                    parser_use_llm=False,
                    rerank_use_llm=True,
                    use_keyword_rules=False,
                    use_hybrid_retrieval=True,
                    case_ids=case_ids or None,
                )
                ablation_results['hybrid_live_llm'] = {
                    'status': 'completed',
                    'top3_hit_rate_pct': r['top3_hit_rate_pct'],
                    'top5_hit_rate_pct': r['top5_hit_rate_pct'],
                    'top3_hits': r['top3_hits'],
                    'top5_hits': r['top5_hits'],
                    'total': r['total'],
                    'pipeline': r['pipeline'],
                    'llm_evidence': r['llm_evidence'],
                    'retrieval_evidence': r['retrieval_evidence'],
                }
        ablation_dir = BASE_DIR / 'reports' / 'ablation'
        ablation_dir.mkdir(parents=True, exist_ok=True)
        ablation_name = (
            'ablation_official_topk.json'
            if args.split == 'all'
            else f'ablation_official_topk_{args.split}.json'
        )
        ablation_path = ablation_dir / ablation_name
        with open(ablation_path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    'generated_at': datetime.now().isoformat(),
                    'task': 'official_topk',
                    'split': args.split,
                    'modes': ablation_results,
                    'note': ('Keyword, hybrid retrieval, and real-LLM modes are isolated. '
                             'A live LLM mode is valid only when trace evidence is present.'),
                },
                f, ensure_ascii=False, indent=2,
            )
        print(f"  Ablation saved to: {ablation_path}")
        for mode_name, r in ablation_results.items():
            if r.get('status') == 'skipped':
                print(f"    {mode_name}: skipped ({r.get('reason', 'unknown')})")
            else:
                print(f"    {mode_name}: top3={r['top3_hit_rate_pct']}% top5={r['top5_hit_rate_pct']}%")

    if run_all or args.composition:
        print('\n>>> Composition Evaluation (official) ...')
        plan = CompositionPlanner()
        dp = DemandParser()
        comp_result = eval_composition(plan, dp, use_llm=parser_use_llm)
        print(f"  Avg Score: {comp_result['avg_score']}")
        results['composition_evaluation'] = comp_result

    print('\n' + '=' * 60)
    print('SUMMARY')
    print('=' * 60)
    if 'intent_evaluation' in results:
        r = results['intent_evaluation']
        print(f"  Intent Accuracy: {r['accuracy_pct']}%")
    if 'tag_evaluation' in results:
        r = results['tag_evaluation']
        print(f"  Tag Accuracy: {r['accuracy_pct']}%")
    if 'topk_evaluation' in results:
        r = results['topk_evaluation']
        print(f"  Top3 Hit Rate: {r['top3_hit_rate_pct']}%")
        print(f"  Top5 Hit Rate: {r['top5_hit_rate_pct']}%")
    if 'composition_evaluation' in results:
        r = results['composition_evaluation']
        print(f"  Composition Avg Score: {r['avg_score']}")

    if should_save_metric_report(results, args.output):
        save_results(results, split=args.split, output=args.output)
    else:
        print('\nNo official metric report written for ablation-only run.')
    print('\nEvaluation complete!')


if __name__ == '__main__':
    main()
