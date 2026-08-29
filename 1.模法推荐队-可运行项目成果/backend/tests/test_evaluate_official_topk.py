import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "evaluate_official_topk.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("evaluate_official_topk", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluation_preserves_unrelated_reports(tmp_path: Path) -> None:
    module = _load_script()
    output_dir = tmp_path / "official_eval"
    output_dir.mkdir()
    evidence = output_dir / "leakage_audit.json"
    evidence.write_text('{"status": "verified"}', encoding="utf-8")

    module.REPORTS_DIR = output_dir
    module.main()

    assert evidence.read_text(encoding="utf-8") == '{"status": "verified"}'
    assert {
        "official_topk_summary.json",
        "val_results.json",
        "test_results.json",
        "official_failures.json",
        "official_topk_report.md",
    }.issubset(path.name for path in output_dir.iterdir())
