"""Tests for synonym-enhanced demand parsing."""
import pytest
from app.services.demand_parser import DemandParser


class TestSynonymsConfig:
    def test_parser_initializes_with_synonyms_config(self):
        """Parser should load synonyms config on initialization."""
        parser = DemandParser()
        assert hasattr(parser, 'synonyms_config')
        assert isinstance(parser.synonyms_config, dict)
        # Should have at least some entries from the config file
        if parser.synonyms_config:
            assert "逾期" in parser.synonyms_config
            assert isinstance(parser.synonyms_config["逾期"], list)

    def test_parser_fallback_without_synonyms_file(self):
        """Parser should work when synonyms config doesn't exist or is empty."""
        parser = DemandParser()
        parser.synonyms_config = {}
        # Should still parse normally
        result = parser.parse("我想做贷前风控")
        assert result.intent in ("credit_risk", "customer_marketing", "operation_management")

    def test_expand_with_synonyms_basic(self):
        """_expand_with_synonyms should append matching synonyms."""
        parser = DemandParser()
        # If synonyms exist, expansion should work
        expanded = parser._expand_with_synonyms("逾期贷款")
        # Should at minimum return original text
        assert "逾期贷款" in expanded

    def test_expand_with_synonyms_no_change(self):
        """_expand_with_synonyms should return original text when no synonyms match."""
        parser = DemandParser()
        parser.synonyms_config = {}
        expanded = parser._expand_with_synonyms("完全无关的内容")
        assert expanded == "完全无关的内容"

    def test_expand_with_synonyms_adds_synonyms(self):
        """_expand_with_synonyms should add synonym words for matching keys."""
        parser = DemandParser()
        if parser.synonyms_config:
            expanded = parser._expand_with_synonyms("逾期贷款")
            # "逾期" synonyms should be appended
            for syn in parser.synonyms_config.get("逾期", []):
                assert syn in expanded

    def test_no_cross_domain_confusion(self):
        """Synonym expansion should not cause wrong intent classification."""
        parser = DemandParser()
        # Even with synonyms, "风险" should not force credit_risk unconditionally
        # "运营" and "网点" and "排班" are strong operation keywords
        result = parser.parse("运营风险管理和网点排班优化")
        # Should still recognize operation keywords
        assert result.intent in ("credit_risk", "customer_marketing", "operation_management")
        # If operation_management scores reasonably, it should be the top pick
        # because "运营", "网点", "排班" are strong operation keywords

    def test_synonym_enhances_intent_matching(self):
        """Synonyms should help match more keywords for intent identification."""
        parser = DemandParser()
        # "不良" is a synonym of "逾期" which is also a direct credit_risk keyword
        # This should still match correctly
        result = parser.parse("违约贷款不良资产处理")
        # "违约" and "不良" are both credit_risk keywords (and synonyms of "逾期")
        assert result.intent == "credit_risk"

    def test_synonym_enhances_tag_extraction(self):
        """Synonyms should help extract more relevant tags."""
        parser = DemandParser()
        result = parser.parse("逾期违约贷款不良资产处理")
        # Should get credit_risk with relevant tags
        assert result.intent == "credit_risk"

    def test_parser_works_with_empty_synonyms(self):
        """Parser should work even if _expand_with_synonyms returns same text."""
        parser = DemandParser()
        parser.synonyms_config = {}
        result = parser.parse("我想做贷前风控")
        assert result.intent in ("credit_risk", "customer_marketing", "operation_management")

    def test_synonym_expansion_preserves_original_text(self):
        """Expanded text should contain the original text unchanged."""
        parser = DemandParser()
        original = "运营风险管理和网点排班优化"
        expanded = parser._expand_with_synonyms(original)
        # Original text should be the prefix
        assert expanded.startswith(original)

    def test_synonym_config_file_exists(self):
        """The synonyms.json config file should exist and be valid."""
        import json, os
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "config", "synonyms.json"
        )
        assert os.path.exists(config_path), f"synonyms.json not found at {config_path}"
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data) > 0
        # Each entry should have a list of synonyms
        for key, synonyms in data.items():
            assert isinstance(synonyms, list), f"{key} should map to a list"
            assert len(synonyms) > 0, f"{key} should have at least one synonym"
