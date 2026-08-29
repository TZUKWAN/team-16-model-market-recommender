"""Tests for _ensure_list and helper functions in analyze_eval_failures.py."""
import importlib.util
import sys
from pathlib import Path

# Load the script module
script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "analyze_eval_failures.py"
spec = importlib.util.spec_from_file_location("analyze_eval_failures", script_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
_ensure_list = mod._ensure_list
_dedupe_ordered = mod._dedupe_ordered


class TestEnsureList:
    def test_list_input(self):
        assert _ensure_list(["RISK_001", "RISK_002"]) == ["RISK_001", "RISK_002"]

    def test_space_separated_string(self):
        result = _ensure_list("RISK_001 RISK_002")
        assert result == ["RISK_001", "RISK_002"]

    def test_comma_separated_string(self):
        result = _ensure_list("RISK_001,RISK_002")
        assert result == ["RISK_001", "RISK_002"]

    def test_chinese_punctuation_separated(self):
        result = _ensure_list("RISK_001，RISK_002、OPS_003;MKT_004")
        assert result == ["RISK_001", "RISK_002", "OPS_003", "MKT_004"]

    def test_json_array_string(self):
        result = _ensure_list('["RISK_001", "RISK_002"]')
        assert result == ["RISK_001", "RISK_002"]

    def test_empty_input(self):
        assert _ensure_list(None) == []
        assert _ensure_list("") == []
        assert _ensure_list("   ") == []

    def test_single_string(self):
        assert _ensure_list("RISK_001") == ["RISK_001"]

    def test_duplicate_removal(self):
        result = _ensure_list("RISK_001 RISK_001 RISK_002")
        assert result == ["RISK_001", "RISK_002"]

    def test_list_with_whitespace_items(self):
        result = _ensure_list(["RISK_001", "  RISK_002  ", "RISK_001", ""])
        assert result == ["RISK_001", "RISK_002"]

    def test_list_with_none_items(self):
        result = _ensure_list(["RISK_001", None, "RISK_002"])
        assert result == ["RISK_001", "RISK_002"]


class TestDedupeOrdered:
    def test_removes_duplicates(self):
        assert _dedupe_ordered(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

    def test_preserves_order(self):
        assert _dedupe_ordered(["c", "a", "b", "a"]) == ["c", "a", "b"]

    def test_empty_list(self):
        assert _dedupe_ordered([]) == []
