"""Tests for fast, validated serving of the authoritative official report."""

import json

from app.api.v1.evaluation import _load_fresh_official_report, _load_precomputed_metrics


def test_fresh_official_report_is_loaded_without_live_recomputation():
    result = _load_fresh_official_report()

    assert result is not None
    values = {metric.name: metric.value for metric in result.metrics}
    assert values["意图识别准确率"] == 97.12
    assert values["标签转换准确率"] == 99.04
    assert values["Top3 命中率"] == 93.53
    assert values["Top5 命中率"] == 97.12
    assert values["组合适配度"] == 83.5
    assert result.is_mock is False
    assert result.total_samples == 1281
    assert result.total_models_covered == 60


def test_load_precomputed_metrics_maps_official_report(tmp_path):
    report = tmp_path / "eval_official_results.json"
    report.write_text(
        json.dumps(
            {
                "evaluation_metadata": {"generated_at": "2026-07-13T00:00:00+00:00"},
                "intent_evaluation": {"total": 10, "accuracy_pct": 95.0},
                "tag_evaluation": {"total": 10, "accuracy_pct": 91.0},
                "topk_evaluation": {
                    "total": 10,
                    "top3_hit_rate_pct": 88.0,
                    "top5_hit_rate_pct": 96.0,
                    "gold_model_coverage_count": 8,
                },
                "composition_evaluation": {"total": 2, "avg_score": 82.0},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = _load_precomputed_metrics(report)

    assert result is not None
    assert [metric.value for metric in result.metrics] == [95.0, 91.0, 88.0, 96.0, 82.0]
    assert result.overall_score == 90.4
    assert result.total_models_covered == 8
    assert result.total_samples == 32
    assert result.report_generated_at == "2026-07-13T00:00:00+00:00"


def test_load_precomputed_metrics_rejects_incomplete_report(tmp_path):
    report = tmp_path / "eval_official_results.json"
    report.write_text('{"intent_evaluation": {}}', encoding="utf-8")

    assert _load_precomputed_metrics(report) is None
