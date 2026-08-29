"""
Report generation service for creating recommendation reports.
Produces structured markdown reports from parse, recommend, and composition results.
Returns app.schemas.report.ReportResponse so the API contract stays consistent.
"""

from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.schemas.report import ReportResponse, ReportSection
from app.services.llm_client import get_llm_client


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
REPORT_SUMMARY_PROMPT = PROMPT_DIR / "report_summary_system.md"

_SUMMARY_SCORE_DISCLOSURE_PATTERN = re.compile(
    r"(?:综合(?:评分|得分|分数)|推荐(?:评分|得分|分数)|匹配(?:评分|得分|分数|度|率)|"
    r"总分|内部(?:排序)?分|置信度|适配度|准确率|召回率|覆盖率|提升率|匹配率|相似度|"
    r"\b(?:AUC|F1|NDCG|MRR|Recall|Precision|Top[- ]?\d+)\b\s*[:=为]?\s*\d)",
    flags=re.IGNORECASE,
)


class ReportGenerationService:
    """Service for generating comprehensive recommendation reports."""

    def __init__(self, llm_client: Any | None = None):
        self.llm = llm_client or get_llm_client()

    def generate(
        self,
        request_id: str = "",
        parse_result: Optional[dict[str, Any]] = None,
        recommend_result: Optional[dict[str, Any]] = None,
        composition_result: Optional[dict[str, Any]] = None,
        model_result: Optional[dict[str, Any]] = None,
        # API endpoint passes these aliases
        recommendations: Optional[list[dict[str, Any]]] = None,
        composition: Optional[dict[str, Any]] = None,
        include_details: bool = True,
    ) -> ReportResponse:
        """Generate a full recommendation report from available data."""
        parse_result = parse_result or {}
        # Normalize aliases used by the API endpoint
        if recommend_result is None and recommendations is not None:
            recommend_result = {"recommendations": recommendations}
        if composition_result is None and composition is not None:
            composition_result = composition

        report_id = f"rpt-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        sections: list[ReportSection] = []
        sections.append(self._build_overview_section(parse_result))
        sections.append(self._build_understanding_section(parse_result))

        if recommend_result:
            sections.append(self._build_recommendation_section(recommend_result))

        if composition_result:
            sections.append(self._build_composition_section(composition_result))

        sections.append(self._build_data_gap_section(parse_result, recommend_result))

        if include_details and recommend_result:
            sections.append(self._build_evidence_section(recommend_result))

        if model_result:
            sections.append(self._build_model_result_section(model_result))

        sections.append(self._build_implementation_section(composition_result))
        sections.append(self._build_compliance_section(parse_result, recommend_result, composition_result))
        sections.append(self._build_risk_section())

        raw_content = "\n\n".join(
            [f"## {s.title}\n\n{s.content}" for s in sections]
        )

        rule_summary = self._generate_summary(parse_result, recommend_result)
        summary, generation_source, llm_trace_id, llm_fallback_reason = self._generate_summary_with_llm(
            rule_summary,
            parse_result,
            recommend_result,
            composition_result,
        )
        title = "模型推荐报告 - 银行模型市场智能推荐助手"

        return ReportResponse(
            report_id=report_id,
            request_id=request_id,
            generated_at=now,
            format="markdown",
            title=title,
            summary=summary,
            generation_source=generation_source,
            llm_trace_id=llm_trace_id,
            llm_fallback_reason=llm_fallback_reason,
            sections=sections,
            raw_content=raw_content,
        )

    def _build_overview_section(self, parse_result: Optional[dict[str, Any]]) -> ReportSection:
        if not parse_result:
            return ReportSection(title="需求概述", content="用户提交了模型推荐请求。")

        raw_text = parse_result.get("raw_text", "")
        normalized = parse_result.get("normalized_query", "")
        intent = parse_result.get("intent", "")
        domain = parse_result.get("domain", "")
        scenario = parse_result.get("business_scenario", "")

        content = (
            f"**原始输入：** {raw_text}\n\n"
            f"**标准化查询：** {normalized}\n\n"
            f"**识别意图：** {intent}\n\n"
            f"**业务领域：** {domain}\n\n"
            f"**业务场景：** {scenario}"
        )
        return ReportSection(title="需求概述", content=content)

    def _build_understanding_section(self, parse_result: Optional[dict[str, Any]]) -> ReportSection:
        if not parse_result:
            return ReportSection(title="系统理解", content="暂无系统理解数据。")

        tags = parse_result.get("tags", [])
        translation = parse_result.get("business_to_model_translation", "")
        summary_text = parse_result.get("user_confirmable_summary", "")
        expected_outputs = parse_result.get("expected_outputs", [])
        customer_segment = parse_result.get("customer_segment", [])
        data_conditions = parse_result.get("data_conditions", [])

        content = "### 需求标签\n\n"
        for tag in tags:
            content += f"- {tag}\n"

        if customer_segment:
            content += f"\n**目标客群：** {'、'.join(customer_segment)}\n"
        if expected_outputs:
            content += f"\n**期望输出：** {'、'.join(expected_outputs)}\n"
        if data_conditions:
            content += f"\n**所需数据：** {'、'.join(data_conditions)}\n"

        content += f"\n### 业务→模型翻译\n\n{translation}\n"
        content += f"\n### 用户确认摘要\n\n{summary_text}\n"

        return ReportSection(title="系统理解", content=content)

    def _build_recommendation_section(self, recommend_result: dict[str, Any]) -> ReportSection:
        recommendations = recommend_result.get("recommendations", [])
        demo_references = recommend_result.get("demo_references", [])
        catalog_policy = recommend_result.get("catalog_policy", "official")

        if not recommendations:
            return ReportSection(title="推荐模型", content="暂无推荐结果。")

        if catalog_policy == "demo":
            content = (
                "### Demo推荐榜单（非官方）\n\n"
                "> 本榜单来自脱敏Demo目录，仅用于能力展示和方案参考，"
                "不属于官方榜单，不计入官方指标或组合推荐。\n\n"
            )
        else:
            content = "### 官方推荐榜单\n\n"
        content += "| 排名 | 模型名称 | 模型ID | 推荐理由 |\n"
        content += "|------|----------|--------|----------|\n"

        for rec in recommendations[:5]:
            rank = rec.get("rank", "")
            name = rec.get("model_name", "")
            mid = rec.get("model_id", "")
            reason = rec.get("recommendation_reason", "")
            if len(reason) > 60:
                reason = reason[:60] + "..."
            content += f"| {rank} | {name} | {mid} | {reason} |\n"

        if demo_references:
            content += (
                "\n### Demo参考候选（非官方）\n\n"
                "> 以下模型来自脱敏Demo目录，仅用于能力展示和方案参考，"
                "不属于官方榜单，不计入官方指标或组合推荐。\n\n"
                "| 参考序号 | 模型名称 | 模型ID | 来源 |\n"
                "|----------|----------|--------|------|\n"
            )
            for rec in demo_references[:10]:
                content += (
                    f"| {rec.get('rank', '')} | {rec.get('model_name', '')} | "
                    f"{rec.get('model_id', '')} | Demo |\n"
                )

        summary = recommend_result.get("summary", "")
        if summary:
            content += f"\n**总结：** {summary}\n"

        return ReportSection(title="推荐模型列表", content=content)

    def _build_composition_section(self, composition_result: dict[str, Any]) -> ReportSection:
        if not composition_result:
            return ReportSection(title="组合方案", content="暂无组合方案。")

        name = composition_result.get("composition_name", "")
        scenario = composition_result.get("scenario", "")
        nodes = composition_result.get("nodes", [])

        content = f"**方案名称：** {name}\n\n"
        content += f"**适用场景：** {scenario}\n\n"
        content += "### 流程步骤\n\n"

        for node in nodes:
            step_order = node.get("step_order", "")
            model_name = node.get("model_name", "")
            capability = node.get("capability", "")
            inputs = node.get("input_fields", node.get("input_requirements", []))
            outputs = node.get("output_fields", node.get("output_requirements", []))
            content += (
                f"**Step {step_order}：{model_name}（{capability}）**\n\n"
                f"- 输入：{'、'.join(inputs)}\n"
                f"- 输出：{'、'.join(outputs)}\n\n"
            )

        business_exp = composition_result.get("business_explanation", "")
        if business_exp:
            content += f"### 业务解释\n\n{business_exp}\n"

        return ReportSection(title="最佳组合方案", content=content)

    def _build_data_gap_section(
        self, parse_result: Optional[dict[str, Any]], recommend_result: Optional[dict[str, Any]]
    ) -> ReportSection:
        content = ""

        if parse_result:
            data_conditions = parse_result.get("data_conditions", [])
            if data_conditions:
                content += "**所需数据：**\n\n"
                for d in data_conditions:
                    content += f"- {d}\n"
                content += "\n"

        if recommend_result:
            all_missing: list[str] = []
            for rec in recommend_result.get("recommendations", []):
                missing = rec.get("missing_data", [])
                all_missing.extend(missing)

            unique_missing = list(dict.fromkeys(all_missing))
            if unique_missing:
                content += "**数据缺口：**\n\n"
                for m in unique_missing:
                    content += f"- ⚠ {m}\n"
                content += "\n"

        if not content:
            content = "数据条件基本满足，无需额外补充。"

        return ReportSection(title="所需数据与缺口分析", content=content)

    def _build_evidence_section(self, recommend_result: dict[str, Any]) -> ReportSection:
        recommendations = recommend_result.get("recommendations", [])

        if not recommendations:
            return ReportSection(title="详细证据", content="暂无证据数据。")

        content = ""
        for rec in recommendations[:3]:
            model_name = rec.get("model_name", "")
            evidence_cards = rec.get("evidence_cards", [])

            if evidence_cards:
                content += f"### {model_name} 证据卡片\n\n"
                for card in evidence_cards:
                    etype = card.get("evidence_type", "")
                    etext = card.get("evidence_text", "")
                    content += f"- **[{etype}]** {etext}\n"
                content += "\n"

        if not content:
            content = "暂无可展示的推荐证据卡片。"
        return ReportSection(title="推荐依据与证据详情", content=content)

    def _build_model_result_section(self, model_result: dict[str, Any]) -> ReportSection:
        payload = model_result.get("result", model_result)
        if not isinstance(payload, dict):
            return ReportSection(title="模型结果样例", content="暂无可展示模型结果样例。")

        rows = payload.get("rows", [])
        result_type = payload.get("result_type", "")
        notice = payload.get("desensitized_notice") or payload.get("compliance_notice", "")
        usage_boundary = payload.get("usage_boundary", "")

        content = ""
        if result_type:
            content += f"**结果类型：** {result_type}\n\n"
        if notice:
            content += f"**脱敏说明：** {notice}\n\n"
        if usage_boundary:
            content += f"**用途边界：** {usage_boundary}\n\n"

        if isinstance(rows, list) and rows:
            sample_rows = rows[:5]
            columns = list(sample_rows[0].keys()) if isinstance(sample_rows[0], dict) else []
            if columns:
                content += "### 结果样例\n\n"
                content += "| " + " | ".join(columns) + " |\n"
                content += "| " + " | ".join(["---"] * len(columns)) + " |\n"
                for row in sample_rows:
                    if isinstance(row, dict):
                        content += "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |\n"
        if not content:
            content = "模型调用已完成，但未返回结构化结果样例。"

        return ReportSection(title="模型结果样例", content=content)

    def _build_implementation_section(
        self, composition_result: Optional[dict[str, Any]]
    ) -> ReportSection:
        if not composition_result:
            return ReportSection(
                title="实施建议",
                content=(
                    "1. 优先部署排名第一的推荐模型\n"
                    "2. 收集并准备所需数据\n"
                    "3. 进行模型效果验证\n"
                    "4. 逐步放量上线"
                ),
            )

        usage_guide = composition_result.get("usage_guide", [])
        if not usage_guide:
            return ReportSection(title="实施建议", content="暂无详细实施指南。")

        content = ""
        for guide in usage_guide:
            if isinstance(guide, dict):
                step = guide.get("step", "")
                desc = guide.get("description", "")
                time_est = guide.get("estimated_time", "")
                data_prep = guide.get("data_preparation", "")
                content += (
                    f"**{step}**\n\n"
                    f"- 描述：{desc}\n"
                    f"- 预计时间：{time_est}\n"
                    f"- 数据准备：{data_prep}\n\n"
                )
            else:
                content += f"{guide}\n\n"

        return ReportSection(title="实施指南", content=content)

    def _build_compliance_section(
        self,
        parse_result: Optional[dict[str, Any]],
        recommend_result: Optional[dict[str, Any]],
        composition_result: Optional[dict[str, Any]],
    ) -> ReportSection:
        domain = (parse_result or {}).get("intent", "")
        output_types = (parse_result or {}).get("expected_outputs", [])
        recommendations = (recommend_result or {}).get("recommendations", [])
        model_ids = [rec.get("model_id", "") for rec in recommendations[:5] if rec.get("model_id")]
        execution = (composition_result or {}).get("execution_result", {})
        execution_notice = execution.get("desensitized_notice", "")

        content = (
            "1. 推荐、组合和调用结果默认按脱敏演示口径展示，不包含真实客户明细。\n"
            "2. 风控名单、营销名单和运营预警仅能在授权业务场景内使用，禁止跨机构、跨用途扩散。\n"
            "3. 模型输出必须作为人工复核和策略辅助依据，不得作为唯一自动化决策依据。\n"
            "4. 导出、共享或落地调用前，应复核用户角色、机构权限、数据授权和留痕要求。\n"
        )
        if domain:
            content += f"\n**识别意图：** {domain}\n"
        if output_types:
            content += f"\n**涉及输出：** {'、'.join(output_types)}\n"
        if model_ids:
            content += f"\n**涉及模型：** {'、'.join(model_ids)}\n"
        if execution_notice:
            content += f"\n**组合执行说明：** {execution_notice}\n"

        return ReportSection(title="合规与用途边界", content=content)

    def _build_risk_section(self) -> ReportSection:
        content = (
            "1. 模型预测结果基于历史数据，市场环境变化可能影响预测准确性\n"
            "2. 建议设置人工复核通道，避免完全依赖模型决策\n"
            "3. 模型需要定期迭代更新以保持效果稳定\n"
            "4. 数据隐私和合规要求需在部署前确认\n"
            "5. 建议在正式上线前进行充分的A/B测试\n"
        )
        return ReportSection(title="风险提示", content=content)

    def _generate_summary(
        self, parse_result: Optional[dict[str, Any]], recommend_result: Optional[dict[str, Any]]
    ) -> str:
        summary_parts: list[str] = []

        if parse_result:
            scenario = parse_result.get("business_scenario", "")
            if scenario:
                summary_parts.append(f"针对「{scenario}」场景")

        if recommend_result:
            recs = recommend_result.get("recommendations", [])
            if recs:
                top_name = recs[0].get("model_name", "")
                summary_parts.append(
                    f"推荐首选模型「{top_name}」"
                )

        if not summary_parts:
            return "已为您生成了模型推荐报告。"

        summary_parts.append("详细内容请参见报告正文。")
        return "。".join(summary_parts)

    def _generate_summary_with_llm(
        self,
        rule_summary: str,
        parse_result: dict[str, Any],
        recommend_result: Optional[dict[str, Any]],
        composition_result: Optional[dict[str, Any]],
    ) -> tuple[str, str, str, str]:
        """Generate an executive summary with LLM when configured; otherwise keep rule output."""
        if not getattr(self.llm, "available", False):
            return rule_summary, "rule", "", "llm_not_configured"

        system_prompt = self._load_report_prompt()
        user_message = self._build_report_summary_payload(
            rule_summary,
            parse_result,
            recommend_result,
            composition_result,
        )
        result = self.llm.chat_json(
            system_prompt,
            user_message,
            temperature=0.2,
            prompt_version="recommendation-report-summary-v1",
            cache_context={
                "recommendation_present": recommend_result is not None,
                "composition_present": composition_result is not None,
            },
        )
        trace_id = getattr(self.llm, "last_trace_id", "")
        if not result:
            reason = str(getattr(self.llm, "last_call_status", {}).get("reason") or "invalid_llm_result")[:80]
            return rule_summary, "fallback", trace_id, reason

        summary = str(result.get("summary", "")).strip()
        if not summary or len(summary) > 240:
            return rule_summary, "fallback", trace_id, "invalid_summary"
        if _SUMMARY_SCORE_DISCLOSURE_PATTERN.search(summary):
            return rule_summary, "fallback", trace_id, "score_disclosure"

        return summary, "llm", trace_id, ""

    def _load_report_prompt(self) -> str:
        try:
            return REPORT_SUMMARY_PROMPT.read_text(encoding="utf-8")
        except OSError:
            return (
                "你是银行模型市场推荐助手的报告撰写专家。"
                "请只输出 JSON，字段为 summary。摘要必须客观、可审计、中文、120字以内。"
            )

    def _build_report_summary_payload(
        self,
        rule_summary: str,
        parse_result: dict[str, Any],
        recommend_result: Optional[dict[str, Any]],
        composition_result: Optional[dict[str, Any]],
    ) -> str:
        recommendations = (recommend_result or {}).get("recommendations", [])[:3]
        top_models = [
            {
                "rank": rec.get("rank", ""),
                "model_name": rec.get("model_name", ""),
                "reason": rec.get("recommendation_reason", ""),
            }
            for rec in recommendations
        ]
        payload = {
            "rule_summary": rule_summary,
            "demand": {
                "raw_text": parse_result.get("raw_text", ""),
                "intent": parse_result.get("intent", ""),
                "domain": parse_result.get("domain", ""),
                "business_scenario": parse_result.get("business_scenario", ""),
                "expected_outputs": parse_result.get("expected_outputs", []),
                "data_conditions": parse_result.get("data_conditions", []),
            },
            "top_models": top_models,
            "composition": {
                "name": (composition_result or {}).get("composition_name", ""),
            },
        }
        import json

        return json.dumps(payload, ensure_ascii=False)
