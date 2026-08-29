"""Regression tests for split-safe official evaluation and LLM evidence."""

import importlib.util
from pathlib import Path

from app.services.demand_parser import DemandParser
from app.services.recommender import ModelRecommendationService


ROOT = Path(__file__).resolve().parents[2]


def load_script():
    path = ROOT / "scripts" / "run_official_eval.py"
    spec = importlib.util.spec_from_file_location("run_official_eval", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_filter_split_keeps_official_partition_boundaries():
    module = load_script()
    rows = module.load_jsonl(module.EVAL_DIR / "topk_eval_official.jsonl")

    assert len(module.filter_split(rows, "train")) == 291
    assert len(module.filter_split(rows, "val")) == 64
    assert len(module.filter_split(rows, "test")) == 62
    assert len(module.filter_split(rows, "all")) == 417


def test_llm_requested_is_not_reported_as_executed_without_trace(monkeypatch):
    module = load_script()
    sample = {
        "test_id": "test_one",
        "query": "信用卡账单分期概率预测应该选择哪个模型？",
        "gold_model_id": "OFFICIAL_054",
        "gold_model_name": "贷记卡账单分期营销模型",
    }
    monkeypatch.setattr(module, "load_jsonl", lambda path: [sample])
    parser = DemandParser()
    recommender = ModelRecommendationService()
    assert parser.llm.available is False
    assert recommender.llm.available is False

    result = module.eval_topk(
        recommender,
        parser,
        use_llm=True,
        use_keyword_rules=False,
        use_hybrid_retrieval=True,
        split="test",
    )

    assert result["pipeline"]["use_llm_requested"] is True
    assert result["pipeline"]["llm_available"] is False
    assert result["llm_evidence"]["trace_case_count"] == 0
    assert result["llm_evidence"]["rerank_attempt_count"] == 0
    assert result["retrieval_evidence"]["dense_available_case_count"] == 0
    assert result["retrieval_evidence"]["retrieval_mode_counts"] == {"sparse": 1}
    assert result["details"][0]["parse_source"] == "rule"


def test_ablation_only_metadata_cannot_overwrite_metric_report():
    module = load_script()

    assert module.should_save_metric_report({"evaluation_metadata": {}}, "") is False
    assert module.should_save_metric_report(
        {"evaluation_metadata": {}, "topk_evaluation": {}}, ""
    ) is True
    assert module.should_save_metric_report({"evaluation_metadata": {}}, "custom.json") is True


def test_topk_report_includes_macro_model_and_scenario_metrics(monkeypatch):
    module = load_script()
    rows = [
        {
            "test_id": "test_one",
            "query": "账单分期概率预测",
            "gold_model_id": "OFFICIAL_054",
            "gold_model_name": "贷记卡账单分期模型",
            "scenario": "customer_marketing",
        }
    ]
    monkeypatch.setattr(module, "load_jsonl", lambda path: rows)
    result = module.eval_topk(
        ModelRecommendationService(),
        DemandParser(),
        use_llm=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=True,
        split="test",
    )

    assert result["gold_model_coverage_count"] == 1
    assert result["macro_by_gold_model_top3_pct"] in {0.0, 100.0}
    assert result["per_gold_model"]["OFFICIAL_054"]["total"] == 1
    assert result["per_scenario"]["customer_marketing"]["total"] == 1


def test_compute_provenance_includes_config_asset_and_split_responsibility():
    """Evaluation reports must carry config/asset hashes and split responsibility."""
    module = load_script()
    provenance = module.compute_provenance()

    assert "config_hash_sha256" in provenance
    assert "asset_hash_sha256" in provenance
    assert "official_catalog" in provenance["asset_hash_sha256"]
    assert provenance["asset_hash_sha256"]["official_catalog"] != "missing"
    assert len(provenance["asset_hash_sha256"]["official_catalog"]) == 64
    # Knowledge graph assets must be traceable.
    assert provenance["asset_hash_sha256"]["knowledge_nodes"] != "missing"
    assert provenance["asset_hash_sha256"]["knowledge_edges"] != "missing"
    # Git provenance is best-effort; if git is available, commit sha should be present.
    assert "code_provenance" in provenance


def test_split_responsibility_documented_in_metadata():
    """The frozen split boundary must be documented inside evaluation metadata."""
    module = load_script()
    # Verify the counts used by the eval pipeline match the frozen partition.
    rows = module.load_jsonl(module.EVAL_DIR / "topk_eval_official.jsonl")
    assert len(module.filter_split(rows, "train")) == 291
    assert len(module.filter_split(rows, "val")) == 64
    assert len(module.filter_split(rows, "test")) == 62
    # train + val + test must equal all without overlap.
    all_rows = set(id(r) for r in module.filter_split(rows, "all"))
    train_rows = set(id(r) for r in module.filter_split(rows, "train"))
    val_rows = set(id(r) for r in module.filter_split(rows, "val"))
    test_rows = set(id(r) for r in module.filter_split(rows, "test"))
    assert train_rows | val_rows | test_rows == all_rows
    assert len(train_rows & val_rows) == 0
    assert len(train_rows & test_rows) == 0
    assert len(val_rows & test_rows) == 0


def test_code_provenance_git_source_when_git_available():
    """When git works, provenance must come from git and say so."""
    module = load_script()
    git_info = module._git_provenance()
    if not git_info.get("commit_sha"):
        import pytest
        pytest.skip("git is not available in this environment")
    provenance = module.compute_provenance()
    code = provenance["code_provenance"]
    assert code["provenance_source"] == "git"
    assert code["commit_sha"] == git_info["commit_sha"]
    assert code["branch"]


def test_code_provenance_environment_fallback(monkeypatch):
    """Without git, complete SOURCE_* env vars must drive provenance."""
    module = load_script()
    monkeypatch.setattr(module, "_git_provenance", lambda: {})
    monkeypatch.setenv("SOURCE_COMMIT", "cf8061e1563ad8d80f55dcfcc2cefa13bbfdf988")
    monkeypatch.setenv("SOURCE_BRANCH", "audit/score-visibility-data-integrity")
    monkeypatch.setenv("SOURCE_WORKTREE_DIRTY", "true")

    code = module.compute_provenance()["code_provenance"]

    assert code["provenance_source"] == "environment_fallback"
    assert code["commit_sha"] == "cf8061e1563ad8d80f55dcfcc2cefa13bbfdf988"
    assert code["branch"] == "audit/score-visibility-data-integrity"
    assert code["working_tree_dirty"] is True
    assert code["short_sha"] == "cf8061e"


def test_code_provenance_unknown_when_git_and_env_unavailable(monkeypatch):
    """With neither git nor complete env vars, source is unknown — never faked."""
    module = load_script()
    monkeypatch.setattr(module, "_git_provenance", lambda: {})
    monkeypatch.delenv("SOURCE_COMMIT", raising=False)
    monkeypatch.delenv("SOURCE_BRANCH", raising=False)
    monkeypatch.delenv("SOURCE_WORKTREE_DIRTY", raising=False)

    code = module.compute_provenance()["code_provenance"]

    assert code == {"provenance_source": "unknown"}
    assert "commit_sha" not in code


def test_code_provenance_partial_env_not_used(monkeypatch):
    """A partial environment (missing dirty flag) must not yield half-credible data."""
    module = load_script()
    monkeypatch.setattr(module, "_git_provenance", lambda: {})
    monkeypatch.setenv("SOURCE_COMMIT", "cf8061e1563ad8d80f55dcfcc2cefa13bbfdf988")
    monkeypatch.setenv("SOURCE_BRANCH", "audit/score-visibility-data-integrity")
    monkeypatch.delenv("SOURCE_WORKTREE_DIRTY", raising=False)

    code = module.compute_provenance()["code_provenance"]

    assert code == {"provenance_source": "unknown"}


def test_topk_retrieval_evidence_includes_dense_runtime_summary(monkeypatch):
    """TopK reports must carry a dense runtime summary (mode, manifest, dim, revision)."""
    module = load_script()
    rows = [
        {
            "test_id": "test_one",
            "query": "账单分期概率预测",
            "gold_model_id": "OFFICIAL_054",
            "gold_model_name": "贷记卡账单分期模型",
            "scenario": "customer_marketing",
        }
    ]
    monkeypatch.setattr(module, "load_jsonl", lambda path: rows)
    result = module.eval_topk(
        ModelRecommendationService(),
        DemandParser(),
        use_llm=False,
        use_keyword_rules=False,
        use_hybrid_retrieval=True,
        split="test",
    )

    runtime = result["retrieval_evidence"]["dense_runtime"]
    for key in (
        "retrieval_runtime_mode",
        "dense_available",
        "dense_manifest_verified",
        "dense_embedding_dimension",
        "dense_expected_revision",
        "dense_offline",
    ):
        assert key in runtime
