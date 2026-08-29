"""
Evaluation metrics endpoint - GET /api/v1/evaluation/metrics
Returns computed evaluation metrics based on actual data.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.schemas.evaluation import EvaluationMetricsResponse, MetricDetail
from app.services.data_loader import load_eval_sets, load_tags, get_tag_key_to_name
from app.services.composition_planner import CompositionPlanner
from app.services.demand_parser import DemandParser
from app.services.recommender import ModelRecommendationService
from app.repositories.model_asset_repository import get_model_asset_repository

router = APIRouter()


def _load_precomputed_metrics(report_path: Path | None = None) -> EvaluationMetricsResponse | None:
    """Load the checked-in official evaluation report without recomputing it.

    Re-running the full 417-sample evaluation in an HTTP request blocks the
    worker for tens of seconds. The project already ships a reproducible report,
    so the dashboard endpoint should read that artifact and leave regeneration
    to the offline evaluation script.
    """
    from app.core.config import get_settings

    path = report_path or (
        get_settings().BASE_DIR / "reports" / "official" / "eval_official_results.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        intent = payload["intent_evaluation"]
        tags = payload["tag_evaluation"]
        topk = payload["topk_evaluation"]
        composition = payload["composition_evaluation"]
    except (OSError, ValueError, KeyError, TypeError):
        return None

    intent_acc = float(intent.get("accuracy_pct", 0.0))
    tag_acc = float(tags.get("accuracy_pct", 0.0))
    top3_rate = float(topk.get("top3_hit_rate_pct", 0.0))
    top5_rate = float(topk.get("top5_hit_rate_pct", 0.0))
    combo_fitness = float(composition.get("avg_score", 0.0))

    intent_total = int(intent.get("total", 0))
    tag_total = int(tags.get("total", 0))
    topk_total = int(topk.get("total", 0))
    combo_total = int(composition.get("total", 0))
    metrics = [
        MetricDetail(name="意图识别准确率", value=intent_acc, target=93.0, unit="%", is_met=intent_acc >= 93.0, sample_count=intent_total),
        MetricDetail(name="标签转换准确率", value=tag_acc, target=90.0, unit="%", is_met=tag_acc >= 90.0, sample_count=tag_total),
        MetricDetail(name="Top3 命中率", value=top3_rate, target=85.0, unit="%", is_met=top3_rate >= 85.0, sample_count=topk_total),
        MetricDetail(name="Top5 命中率", value=top5_rate, target=92.0, unit="%", is_met=top5_rate >= 92.0, sample_count=topk_total),
        MetricDetail(name="组合适配度", value=combo_fitness, target=80.0, unit="%", is_met=combo_fitness >= 80.0, sample_count=combo_total),
    ]
    metadata = payload.get("evaluation_metadata", {})
    generated_at = metadata.get("generated_at")
    if not generated_at:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()

    coverage = topk.get("gold_model_coverage_count", 60)
    overall = sum(metric.value for metric in metrics) / len(metrics)
    return EvaluationMetricsResponse(
        metrics=metrics,
        overall_score=round(overall, 1),
        report_generated_at=str(generated_at),
        is_mock=False,
        total_models_covered=int(coverage or 60),
        total_samples=intent_total + tag_total + topk_total + combo_total,
    )


def _load_jsonl(path: Path) -> list[dict]:
    """Load a JSONL file into a list of dicts."""
    records = []
    if not path.exists():
        return records
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception:
        pass
    return records


def _demo_eval_metrics() -> EvaluationMetricsResponse:
    """Fallback demo evaluation metrics when official files are missing."""
    models = get_model_asset_repository().list_models()
    eval_sets = load_eval_sets()

    parser = DemandParser()
    intent_samples = eval_sets.get("intent_eval", [])
    intent_correct = 0
    for s in intent_samples:
        raw = s.get("query", s.get("raw_text", ""))
        gold = s.get("expected_domain", s.get("gold_intent", ""))
        if raw and gold:
            result = parser.parse(raw, use_llm=False)
            if result.intent == gold:
                intent_correct += 1
    intent_acc = round(intent_correct / len(intent_samples) * 100, 1) if intent_samples else 0.0

    tag_samples = eval_sets.get("tag_eval", [])
    tag_precision = tag_recall = tag_f1 = 0.0
    if tag_samples:
        total_p = total_r = 0.0
        for s in tag_samples:
            raw = s.get("query", s.get("raw_text", ""))
            expected = set(s.get("expected_tags", []))
            if raw and expected:
                result = parser.parse(raw, use_llm=False)
                pred = set(result.tag_names)
                tp = len(pred & expected)
                p = tp / len(pred) if pred else 0
                r = tp / len(expected) if expected else 0
                total_p += p
                total_r += r
        tag_precision = round(total_p / len(tag_samples), 3) if tag_samples else 0
        tag_recall = round(total_r / len(tag_samples), 3) if tag_samples else 0
        tag_f1 = round(2 * tag_precision * tag_recall / (tag_precision + tag_recall), 3) if (tag_precision + tag_recall) > 0 else 0

    topk_samples = eval_sets.get("topk_eval", [])
    recommender = ModelRecommendationService()
    top3_hits = top5_hits = 0
    for s in topk_samples:
        query = s.get("query", "")
        gold_ids = set(s.get("expected_model_ids", []))
        if query and gold_ids:
            parse_result = parser.parse(query, use_llm=False)
            result = recommender.recommend(
                parse_result.model_dump(),
                top_k=5,
                use_llm=False,
                use_keyword_rules=False,
                use_hybrid_retrieval=True,
            )
            rec_ids = [r.model_id for r in result.recommendations]
            if any(g in rec_ids[:3] for g in gold_ids):
                top3_hits += 1
            if any(g in rec_ids for g in gold_ids):
                top5_hits += 1

    top3_rate = round(top3_hits / len(topk_samples) * 100, 1) if topk_samples else 0.0
    top5_rate = round(top5_hits / len(topk_samples) * 100, 1) if topk_samples else 0.0

    total_samples = len(intent_samples) + len(tag_samples) + len(topk_samples)
    metrics = [
        MetricDetail(name="意图识别准确率", value=intent_acc, target=85.0, unit="%", is_met=intent_acc >= 85.0, sample_count=len(intent_samples)),
        MetricDetail(name="标签转换准确率", value=round(tag_f1 * 100, 1), target=80.0, unit="%", is_met=tag_f1 * 100 >= 80.0, sample_count=len(tag_samples)),
        MetricDetail(name="Top3命中率", value=top3_rate, target=70.0, unit="%", is_met=top3_rate >= 70.0, sample_count=len(topk_samples)),
        MetricDetail(name="Top5命中率", value=top5_rate, target=85.0, unit="%", is_met=top5_rate >= 85.0, sample_count=len(topk_samples)),
        MetricDetail(name="组合适配度", value=67.5, target=75.0, unit="%", is_met=False, sample_count=0),
    ]
    overall = (intent_acc + round(tag_f1 * 100, 1) + top3_rate + top5_rate + 67.5) / 5.0

    return EvaluationMetricsResponse(
        metrics=metrics,
        overall_score=round(overall, 1),
        report_generated_at=datetime.now(timezone.utc).isoformat(),
        is_mock=True,
        total_models_covered=len(models),
        total_samples=total_samples,
    )


def _load_fresh_official_report() -> EvaluationMetricsResponse | None:
    """Serve the audited offline report when it is newer than its data/config inputs."""
    from app.core.config import get_settings

    settings = get_settings()
    report_path = settings.BASE_DIR / "reports" / "official" / "eval_official_results.json"
    source_paths = [
        settings.DATA_DIR / "eval_official" / "intent_eval_official.jsonl",
        settings.DATA_DIR / "eval_official" / "tag_eval_official.jsonl",
        settings.DATA_DIR / "eval_official" / "topk_eval_official.jsonl",
        settings.DATA_DIR / "eval_official" / "combo_eval_official_manual.jsonl",
        settings.DATA_DIR / "official" / "model_catalog_structured.jsonl",
        settings.DATA_DIR / "config" / "recommendation_weights.json",
    ]
    if not report_path.exists() or any(not path.exists() for path in source_paths):
        return None
    try:
        if report_path.stat().st_mtime_ns < max(path.stat().st_mtime_ns for path in source_paths):
            return None
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        metadata = report.get("evaluation_metadata", {})
        if metadata.get("split") != "all":
            return None
        if metadata.get("llm_mode") != "off":
            return None
        if metadata.get("keyword_rules") is not False:
            return None
        if metadata.get("hybrid_retrieval") is not True:
            return None

        intent = report["intent_evaluation"]
        tag = report["tag_evaluation"]
        topk = report["topk_evaluation"]
        composition = report["composition_evaluation"]
        if not (
            int(intent.get("total", 0)) == 417
            and int(tag.get("total", 0)) == 417
            and int(topk.get("total", 0)) == 417
            and int(composition.get("total", 0)) >= 30
        ):
            return None

        intent_acc = float(intent["accuracy_pct"])
        tag_acc = float(tag["accuracy_pct"])
        top3_rate = float(topk["top3_hit_rate_pct"])
        top5_rate = float(topk["top5_hit_rate_pct"])
        combo_fitness = float(composition["avg_score"])
        metrics = [
            MetricDetail(name="意图识别准确率", value=intent_acc, target=93.0, unit="%", is_met=intent_acc >= 93.0, sample_count=int(intent["total"])),
            MetricDetail(name="标签转换准确率", value=tag_acc, target=90.0, unit="%", is_met=tag_acc >= 90.0, sample_count=int(tag["total"])),
            MetricDetail(name="Top3 命中率", value=top3_rate, target=85.0, unit="%", is_met=top3_rate >= 85.0, sample_count=int(topk["total"])),
            MetricDetail(name="Top5 命中率", value=top5_rate, target=92.0, unit="%", is_met=top5_rate >= 92.0, sample_count=int(topk["total"])),
            MetricDetail(name="组合适配度", value=combo_fitness, target=80.0, unit="%", is_met=combo_fitness >= 80.0, sample_count=int(composition["total"])),
        ]
        # Top3 and Top5 share the same recommendation cases, so count that
        # dataset once when reporting the number of evaluated samples.
        total_samples = (
            int(intent["total"])
            + int(tag["total"])
            + int(topk["total"])
            + int(composition["total"])
        )
        overall = sum(metric.value for metric in metrics) / len(metrics)
        return EvaluationMetricsResponse(
            metrics=metrics,
            overall_score=round(overall, 1),
            report_generated_at=str(metadata.get("generated_at") or ""),
            is_mock=False,
            total_models_covered=60,
            total_samples=total_samples,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _compute_metrics_live():
    """Compute official metrics live when no fresh audited report is available."""
    from app.core.config import get_settings
    settings = get_settings()
    models = get_model_asset_repository().list_models()
    data_dir = settings.DATA_DIR / "eval_official"

    intent_path = data_dir / "intent_eval_official.jsonl"
    tag_path = data_dir / "tag_eval_official.jsonl"
    topk_path = data_dir / "topk_eval_official.jsonl"
    combo_path = data_dir / "combo_eval_official_manual.jsonl"

    if not all(p.exists() for p in [intent_path, tag_path, topk_path, combo_path]):
        return _demo_eval_metrics()

    parser = DemandParser()
    recommender = ModelRecommendationService()
    planner = CompositionPlanner()

    # Intent evaluation
    intent_samples = _load_jsonl(intent_path)
    intent_correct = 0
    for s in intent_samples:
        raw = s.get("query", "")
        gold = s.get("expected_domain", "")
        if raw and gold:
            result = parser.parse(raw, use_llm=False)
            if result.intent == gold:
                intent_correct += 1
    intent_acc = round(intent_correct / len(intent_samples) * 100, 1) if intent_samples else 0.0

    # Tag evaluation
    tag_samples = _load_jsonl(tag_path)
    tags_data = load_tags()
    key_to_name = get_tag_key_to_name(tags_data)
    name_to_key = {v: k for k, v in key_to_name.items()}

    def normalize_tag(tag: str) -> str:
        tag = str(tag).strip()
        if tag in name_to_key:
            return name_to_key[tag]
        return tag

    tag_correct = 0
    tag_count = 0
    for s in tag_samples:
        raw = s.get("query", "")
        expected = set(s.get("expected_tags", []))
        if raw and expected:
            result = parser.parse(raw, use_llm=False)
            pred_tags = set(normalize_tag(t) for t in result.tags)
            gold_tags = set(normalize_tag(t) for t in expected)
            if pred_tags & gold_tags:
                tag_correct += 1
            tag_count += 1
    tag_acc = round(tag_correct / tag_count * 100, 1) if tag_count > 0 else 0.0

    # TopK evaluation
    topk_samples = _load_jsonl(topk_path)
    top3_hits = top5_hits = 0
    topk_count = 0
    for s in topk_samples:
        query = s.get("query", "")
        gold_ids = set(s.get("expected_model_ids", []))
        gold_name = s.get("gold_model_name", "")
        gold_id = s.get("gold_model_id", "")
        if gold_id:
            gold_ids.add(gold_id)
        if query:
            parse_result = parser.parse(query, use_llm=False)
            parse_dict = parse_result.model_dump()
            parse_dict["model_source"] = "official"
            result = recommender.recommend(
                parse_dict,
                top_k=5,
                use_llm=False,
                use_keyword_rules=False,
                use_hybrid_retrieval=True,
            )
            rec_ids = [r.model_id for r in result.recommendations]
            rec_names = [r.model_name for r in result.recommendations]
            top3_match = any(g in rec_ids[:3] for g in gold_ids) or (gold_name and gold_name in rec_names[:3])
            top5_match = any(g in rec_ids for g in gold_ids) or (gold_name and gold_name in rec_names)
            if top3_match:
                top3_hits += 1
            if top5_match:
                top5_hits += 1
            topk_count += 1

    top3_rate = round(top3_hits / topk_count * 100, 1) if topk_count > 0 else 0.0
    top5_rate = round(top5_hits / topk_count * 100, 1) if topk_count > 0 else 0.0

    # Composition evaluation
    combo_samples = _load_jsonl(combo_path)
    combo_score_sum = 0.0
    combo_count = 0
    for s in combo_samples:
        query = s.get("query", "")
        if query:
            parse_result = parser.parse(query, use_llm=False)
            result = planner.plan(parse_result.model_dump())
            combo_score_sum += result.total_score
            combo_count += 1
    combo_fitness = round(combo_score_sum / combo_count, 1) if combo_count > 0 else 0.0

    total_samples = len(intent_samples) + len(tag_samples) + len(topk_samples) + len(combo_samples)

    metrics = [
        MetricDetail(name="意图识别准确率", value=intent_acc, target=93.0, unit="%", is_met=intent_acc >= 93.0, sample_count=len(intent_samples)),
        MetricDetail(name="标签转换准确率", value=tag_acc, target=90.0, unit="%", is_met=tag_acc >= 90.0, sample_count=len(tag_samples)),
        MetricDetail(name="Top3 命中率", value=top3_rate, target=85.0, unit="%", is_met=top3_rate >= 85.0, sample_count=topk_count),
        MetricDetail(name="Top5 命中率", value=top5_rate, target=92.0, unit="%", is_met=top5_rate >= 92.0, sample_count=topk_count),
        MetricDetail(name="组合适配度", value=combo_fitness, target=80.0, unit="%", is_met=combo_fitness >= 80.0, sample_count=combo_count),
    ]
    overall = (intent_acc + tag_acc + top3_rate + top5_rate + combo_fitness) / 5.0

    return EvaluationMetricsResponse(
        metrics=metrics,
        overall_score=round(overall, 1),
        report_generated_at=datetime.now(timezone.utc).isoformat(),
        is_mock=False,
        total_models_covered=60,
        total_samples=total_samples,
    )


def _compute_metrics():
    """Return a validated fresh report, falling back to a live recomputation."""
    return _load_fresh_official_report() or _compute_metrics_live()


@router.get("/evaluation/metrics", response_model=EvaluationMetricsResponse)
async def get_evaluation_metrics():
    """Return the latest checked-in official metrics without blocking the API."""
    metrics = _load_precomputed_metrics()
    if metrics is None:
        raise HTTPException(
            status_code=503,
            detail="官方评估报告不可用，请先运行 scripts/run_official_eval.py 重新生成。",
        )
    return metrics
