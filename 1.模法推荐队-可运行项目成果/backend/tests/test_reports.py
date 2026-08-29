"""
Tests for ReportGenerationService.
"""

import pytest
from app.services.report_service import ReportGenerationService


@pytest.fixture
def service():
    return ReportGenerationService()


class FakeLLM:
    def __init__(self, result=None, available=True, trace_id="llm_report_trace"):
        self.result = result
        self.available = available
        self.last_trace_id = trace_id
        self.calls = []
        self.last_call_status = {"status": "fallback", "reason": "circuit_open"} if result is None else {"status": "success"}

    def chat_json(self, system_prompt, user_message, temperature=0.1, **kwargs):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "temperature": temperature,
                "options": kwargs,
            }
        )
        return self.result


@pytest.fixture
def marketing_parse():
    return {
        "raw_text": "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。",
        "normalized_query": "筛选县域新客 首贷营销 转化概率排名名单",
        "intent": "customer_marketing",
        "intent_confidence": 0.94,
        "domain": "客户营销",
        "business_scenario": "县域新客首贷营销",
        "business_stage": "贷前营销",
        "customer_segment": ["县域新客"],
        "expected_outputs": ["营销名单", "转化概率", "客户排序"],
        "data_conditions": ["客户画像", "交易流水", "征信数据"],
        "tags": ["新客", "首贷", "营销转化", "响应预测"],
        "tag_confidence": {"新客": 0.91, "首贷": 0.93, "营销转化": 0.88},
        "business_to_model_translation": "业务需求对应模型任务类型为客户响应预测和转化概率估算。",
        "user_confirmable_summary": "需求确认：您需要为县域新客群体进行首贷营销。",
    }


@pytest.fixture
def marketing_recommend():
    return {
        "request_id": "rec-mkt-001",
        "recommendations": [
            {
                "model_id": "MKT_001",
                "model_name": "县域新客首贷转化预测模型",
                "rank": 1,
                "total_score": 91.5,
                "score_breakdown": {
                    "scenario_match": 95,
                    "customer_match": 93,
                    "data_match": 88,
                    "output_match": 92,
                    "performance": 90,
                    "landing_experience": 88,
                    "compliance": 95,
                },
                "recommendation_reason": "专为县域新客首贷营销场景设计。",
                "evidence_cards": [
                    {
                        "evidence_type": "场景匹配",
                        "evidence_text": "模型明确标注县域新客首贷营销场景标签。",
                        "source_field": "model_tags",
                        "confidence": 0.95,
                    },
                    {
                        "evidence_type": "知识图谱路径",
                        "evidence_text": "图谱路径命中：场景:县域新客首贷营销；输出字段:conversion_probability",
                        "source_field": "knowledge_graph.direct_edges",
                        "confidence": 0.91,
                    }
                ],
                "required_data": ["客户基本信息", "历史交易流水"],
                "missing_data": ["县域宏观指标"],
                "output_fields": ["转化概率", "响应评分", "客户排名"],
                "applicable_boundary": "适用于县域新客首贷营销场景。",
                "unsuitable_conditions": "不适用于存量客户交叉营销。",
                "compliance_notes": "需符合个人信息保护法要求。",
                "alternative_models": [],
            },
            {
                "model_id": "MKT_002",
                "model_name": "新客响应率预测模型",
                "rank": 2,
                "total_score": 87.2,
                "score_breakdown": {
                    "scenario_match": 85,
                    "customer_match": 90,
                    "data_match": 86,
                    "output_match": 88,
                    "performance": 89,
                    "landing_experience": 85,
                    "compliance": 90,
                },
                "recommendation_reason": "聚焦新客响应预测。",
                "evidence_cards": [],
                "required_data": ["客户基本信息"],
                "missing_data": [],
                "output_fields": ["响应概率"],
                "applicable_boundary": "适用于零售新客营销响应预测。",
                "unsuitable_conditions": "",
                "compliance_notes": "",
                "alternative_models": [],
            },
        ],
        "unrecommended_examples": [],
        "summary": "根据营销需求推荐了2个模型。",
    }


@pytest.fixture
def composition_result():
    return {
        "composition_id": "COMP_MKT_001",
        "composition_name": "县域新客首贷营销组合",
        "scenario": "客户营销",
        "total_score": 83.8,
        "nodes": [
            {
                "step_id": "STEP_1",
                "step_order": 1,
                "model_id": "MKT_004",
                "model_name": "首贷客户挖掘模型",
                "capability": "潜客识别",
                "input_fields": ["外部征信数据", "客户行为数据"],
                "output_fields": ["首贷倾向评分", "潜客排名"],
            },
            {
                "step_id": "STEP_2",
                "step_order": 2,
                "model_id": "MKT_001",
                "model_name": "县域新客首贷转化预测模型",
                "capability": "转化预测",
                "input_fields": ["客户基本信息", "历史交易流水"],
                "output_fields": ["转化概率", "响应评分"],
            },
        ],
        "flow_edges": [
            {
                "from_step": "STEP_1",
                "to_step": "STEP_2",
                "reason": "潜客倾向评分作为转化预测的特征输入",
            }
        ],
        "io_compatibility": {},
        "missing_data": ["县域宏观指标"],
        "expected_outputs": ["营销名单", "转化概率排序"],
        "business_explanation": "先识别潜客再预测转化概率。",
        "technical_explanation": "串行流水线架构。",
        "management_explanation": "覆盖潜客挖掘到名单生成。",
        "usage_guide": [
            {
                "step": "Step 1: 部署潜客挖掘模型",
                "description": "接入外部征信数据",
                "estimated_time": "2周",
                "data_preparation": "外部数据源接入",
            },
            {
                "step": "Step 2: 部署转化预测模型",
                "description": "利用银行内部数据训练",
                "estimated_time": "3周",
                "data_preparation": "历史营销数据整理",
            },
        ],
    }


@pytest.fixture
def model_result():
    return {
        "model_id": "MKT_001",
        "task_id": "demo-task-report",
        "status": "completed",
        "demo_data": True,
        "result": {
            "result_type": "marketing",
            "desensitized_notice": "本结果为脱敏演示数据。",
            "usage_boundary": "仅用于授权营销客群筛选。",
            "rows": [
                {
                    "customer_id_masked": "CUST_0001",
                    "product": "首贷产品",
                    "conversion_probability": 0.82,
                    "priority": "high",
                }
            ],
        },
    }


class TestReportGeneration:
    """Tests for report generation service."""

    def test_generate_with_parse_only(self, service, marketing_parse):
        """Should generate report with parse result only."""
        report = service.generate(parse_result=marketing_parse)

        assert report.report_id.startswith("rpt-")
        assert report.generated_at is not None
        assert report.generation_source == "rule"
        assert report.llm_trace_id == ""
        assert "需求概述" in report.raw_content
        assert "系统理解" in report.raw_content
        assert "县域新客首贷营销" in report.raw_content
        assert len(report.sections) >= 2

    def test_generate_with_recommendations(self, service, marketing_parse, marketing_recommend):
        """Should include recommendation tables."""
        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert "推荐模型列表" in report.raw_content
        assert "县域新客首贷转化预测模型" in report.raw_content
        assert "91.5" not in report.raw_content
        assert "综合评分" not in report.raw_content
        assert "置信度" not in report.raw_content
        assert "推荐依据与证据详情" in report.raw_content

    def test_generate_labels_demo_references_separately(
        self, service, marketing_parse, marketing_recommend
    ):
        """Demo references must be visible without being presented as official ranking rows."""
        recommend_result = {
            **marketing_recommend,
            "demo_references": [
                {
                    "model_id": "MKT_099",
                    "model_name": "脱敏营销 Demo 模型",
                    "rank": 1,
                    "total_score": 86.4,
                    "source": "demo",
                }
            ],
        }

        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=recommend_result,
        )

        assert "官方推荐榜单" in report.raw_content
        assert "Demo参考候选（非官方）" in report.raw_content
        assert "脱敏营销 Demo 模型" in report.raw_content
        assert "不计入官方指标或组合推荐" in report.raw_content
        assert "86.4" not in report.raw_content

    def test_generate_labels_explicit_demo_main_ranking_as_non_official(
        self, service, marketing_parse, marketing_recommend
    ):
        """An explicit demo-only request must not reuse the official ranking heading."""
        recommend_result = {
            **marketing_recommend,
            "catalog_policy": "demo",
        }

        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=recommend_result,
        )

        assert "Demo推荐榜单（非官方）" in report.raw_content
        assert "不属于官方榜单" in report.raw_content
        assert "### 官方推荐榜单" not in report.raw_content

    def test_generate_with_composition(self, service, marketing_parse, marketing_recommend, composition_result):
        """Should include composition plan section."""
        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
            composition_result=composition_result,
        )

        assert "最佳组合方案" in report.raw_content
        assert "县域新客首贷营销组合" in report.raw_content
        assert "83.8" not in report.raw_content
        assert "实施指南" in report.raw_content
        assert "合规与用途边界" in report.raw_content
        assert "风险提示" in report.raw_content

    def test_generate_with_result_sample_and_graph_path(
        self, service, marketing_parse, marketing_recommend, composition_result, model_result
    ):
        """Report should include graph evidence, data gaps, result sample, and compliance guidance."""
        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
            composition_result=composition_result,
            model_result=model_result,
        )

        assert "知识图谱路径" in report.raw_content
        assert "县域宏观指标" in report.raw_content
        assert "模型结果样例" in report.raw_content
        assert "customer_id_masked" in report.raw_content
        assert "合规与用途边界" in report.raw_content

    def test_generate_empty_input(self, service):
        """Should handle empty input gracefully."""
        report = service.generate()

        assert report.report_id.startswith("rpt-")
        assert report.summary == "已为您生成了模型推荐报告。"
        assert len(report.sections) >= 2

    def test_generate_markdown_format(self, service, marketing_parse):
        """Generated content should be valid markdown."""
        report = service.generate(parse_result=marketing_parse)

        assert report.raw_content.startswith("##")
        assert "**" in report.raw_content  # bold markers present
        assert report.raw_content.count("## ") >= 2

    def test_summary_with_scenario(self, service, marketing_parse, marketing_recommend):
        """Summary should mention the business scenario and top model."""
        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert "县域新客首贷营销" in report.summary
        assert "县域新客首贷转化预测模型" in report.summary
        assert "91.5" not in report.summary

    def test_llm_summary_success(self, marketing_parse, marketing_recommend):
        """Should use LLM summary when available and valid."""
        llm = FakeLLM(result={"summary": "针对县域新客首贷营销，建议优先验证转化预测模型，并补齐县域宏观指标。"})
        service = ReportGenerationService(llm_client=llm)

        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert report.generation_source == "llm"
        assert report.llm_trace_id == "llm_report_trace"
        assert report.summary == "针对县域新客首贷营销，建议优先验证转化预测模型，并补齐县域宏观指标。"
        assert llm.calls
        assert '"score"' not in llm.calls[0]["user_message"]

    def test_llm_summary_invalid_result_falls_back(self, marketing_parse, marketing_recommend):
        """Should keep rule summary when LLM output is invalid."""
        llm = FakeLLM(result={"summary": ""})
        service = ReportGenerationService(llm_client=llm)

        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert report.generation_source == "fallback"
        assert report.llm_fallback_reason == "invalid_summary"
        assert report.llm_trace_id == "llm_report_trace"
        assert "县域新客首贷营销" in report.summary
        assert "县域新客首贷转化预测模型" in report.summary
        assert "91.5" not in report.summary

    def test_llm_summary_score_disclosure_falls_back(self, marketing_parse, marketing_recommend):
        """LLM must not reintroduce hidden recommendation scores into the report."""
        llm = FakeLLM(result={"summary": "首选转化预测模型，综合评分91.5分，匹配度较高。"})
        service = ReportGenerationService(llm_client=llm)

        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert report.generation_source == "fallback"
        assert report.llm_fallback_reason == "score_disclosure"
        assert "91.5" not in report.summary
        assert "县域新客首贷转化预测模型" in report.summary

    def test_llm_unavailable_uses_rule_summary(self, marketing_parse, marketing_recommend):
        """Should not call LLM when unavailable."""
        llm = FakeLLM(result={"summary": "should not be used"}, available=False)
        service = ReportGenerationService(llm_client=llm)

        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert report.generation_source == "rule"
        assert report.llm_trace_id == ""
        assert llm.calls == []

    def test_evidence_section(self, service, marketing_parse, marketing_recommend):
        """Evidence cards should appear in the report when include_details=True."""
        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
            include_details=True,
        )

        assert "推荐依据与证据详情" in report.raw_content
        assert "场景匹配" in report.raw_content
        assert "95%" not in report.raw_content
        assert "91%" not in report.raw_content

    def test_data_gap_section(self, service, marketing_parse, marketing_recommend):
        """Data gap section should highlight missing data."""
        report = service.generate(
            parse_result=marketing_parse,
            recommend_result=marketing_recommend,
        )

        assert "所需数据与缺口分析" in report.raw_content
        assert "县域宏观指标" in report.raw_content

    def test_sections_order(self, service, marketing_parse):
        """Sections should follow the expected order."""
        report = service.generate(parse_result=marketing_parse)

        section_titles = [s.title for s in report.sections]
        assert section_titles[0] == "需求概述"
        assert section_titles[1] == "系统理解"
