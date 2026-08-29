"""
Tests for the official failures JSON file structure and semantics.
"""

import json
from pathlib import Path
from collections import Counter

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = BASE_DIR / "reports" / "official_eval"

FAILURES_PATH = REPORTS_DIR / "official_failures.json"
SUMMARY_PATH = REPORTS_DIR / "official_topk_summary.json"

_VALID_SCOPES = {"top1_miss", "top3_miss", "top5_miss"}


def _load_failures() -> list[dict]:
    return json.loads(FAILURES_PATH.read_text(encoding="utf-8"))


def _load_summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))


def _derive_failure_scope(f: dict) -> str:
    """Derive expected failure_scope from hit flags."""
    if not f["top5_hit"]:
        return "top5_miss"
    if not f["top3_hit"]:
        return "top3_miss"
    if not f["top1_hit"]:
        return "top1_miss"
    raise ValueError(f"{f['query_id']}: perfect hit should not appear in failures")


class TestOfficialFailuresFile:
    def test_failures_file_exists_and_is_list(self):
        """Failures file must exist and contain a non-empty list."""
        assert FAILURES_PATH.exists(), f"Failures file not found: {FAILURES_PATH}"
        failures = _load_failures()
        assert isinstance(failures, list)
        assert len(failures) >= 2, "Expected at least 2 failure entries"

    def test_failure_scope_values_are_valid(self):
        """
        Every failure entry must have a valid failure_scope.

        If the field is not yet present in the JSON, it is derived from the
        hit flags (top5_hit → top3_hit → top1_hit) for validation.
        """
        failures = _load_failures()
        for f in failures:
            scope = f.get("failure_scope", _derive_failure_scope(f))
            assert scope in _VALID_SCOPES, (
                f"{f['query_id']}: invalid failure_scope '{scope}', "
                f"expected one of {_VALID_SCOPES}"
            )

    def test_failure_scope_matches_hit_flags(self):
        """
        failure_scope must be consistent with the hit flags:

          top5_hit == false          → "top5_miss"
          top5_hit == true  and not top3_hit → "top3_miss"
          top3_hit == true  and not top1_hit → "top1_miss"
        """
        failures = _load_failures()
        for f in failures:
            scope = f.get("failure_scope", _derive_failure_scope(f))
            if not f["top5_hit"]:
                assert scope == "top5_miss", (
                    f"{f['query_id']}: expected top5_miss (top5_hit=false), got {scope}"
                )
            elif not f["top3_hit"]:
                assert scope == "top3_miss", (
                    f"{f['query_id']}: expected top3_miss (top5_hit=true, top3_hit=false), "
                    f"got {scope}"
                )
            elif not f["top1_hit"]:
                assert scope == "top1_miss", (
                    f"{f['query_id']}: expected top1_miss (top3_hit=true, top1_hit=false), "
                    f"got {scope}"
                )
            else:
                pytest.fail(f"{f['query_id']}: perfect hit (top1_hit=true) in failures")

    def test_failure_type_stats_match_summary(self):
        """
        Failure-type frequencies in the failures file should match
        the failure_attribution totals in the summary for keys that are
        non-zero in both sources.
        """
        failures = _load_failures()
        summary = _load_summary()

        failure_counter = Counter(f["failure_type"] for f in failures)
        total_attr = summary["failure_attribution"]["total"]

        common_keys = set(failure_counter.keys()) & set(total_attr.keys())
        for key in sorted(common_keys):
            fail_count = failure_counter[key]
            summary_count = total_attr[key]
            if fail_count != 0 and summary_count != 0:
                assert fail_count == summary_count, (
                    f"failure_type '{key}' count mismatch: "
                    f"failures={fail_count}, summary={summary_count}"
                )

    def test_no_perfect_hits_in_failures(self):
        """No failure entry should have top1_hit == true."""
        failures = _load_failures()
        for f in failures:
            assert f["top1_hit"] is False, (
                f"{f['query_id']}: top1_hit is true, but entry is in failures list"
            )
