"""
explanation_generator.py — Three-mode explanation generator.

Generates Business (业务版), Technical (技术版), and Management (管理版)
explanations for both single model recommendations and composition plans.
"""

from __future__ import annotations
import logging
import json
from pathlib import Path
import re
from typing import Any

from app.schemas.recommendation import RecommendedModel, ScoreBreakdown, EvidenceCard
from app.schemas.composition import RecommendCompositionResponse, CompositionNode
from app.services.llm_client import get_llm_client

logger = logging.getLogger(__name__)
PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
RECOMMENDATION_EXPLANATION_PROMPT = PROMPT_DIR / "recommendation_explanation.md"


class ExplanationGenerator:
    """
    Generates multi-perspective explanations for recommendations.
    Uses LLM only when configured; otherwise keeps rule-based content.
    """

    def __init__(self, llm_client: Any | None = None):
        self.llm = llm_client or get_llm_client()

    @staticmethod
    def generate_model_explanations(
        model: RecommendedModel,
        parse_result: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """
        Generate three-mode explanations for a single model.

        Returns:
            {"business": "...", "technical": "...", "management": "..."}
        """
        pr = parse_result or {}
        query = pr.get("raw_text", "") or pr.get("normalized_query", "") or ""
        expected_outputs = pr.get("expected_outputs", []) or []

        scenario = pr.get("business_scenario", "") or "当前场景"
        name = model.model_name
        sb = model.score_breakdown
        boundary = model.applicable_boundary
        unsuitable = model.unsuitable_conditions
        compliance = model.compliance_notes
        evidence_cards = model.evidence_cards or []

        gaps = _detect_match_gaps(query, model, expected_outputs)

        business = _business_model(
            name, scenario, sb, boundary,
            model.required_data, model.missing_data, model.output_fields, compliance,
            query=query, expected_outputs=expected_outputs, gaps=gaps,
            evidence_cards=evidence_cards, unsuitable=unsuitable,
        )
        technical = _technical_model(
            name, model.model_id, sb, boundary,
            model.required_data, model.missing_data, model.output_fields,
            query=query, expected_outputs=expected_outputs, gaps=gaps,
            evidence_cards=evidence_cards, compliance=compliance, unsuitable=unsuitable,
        )
        management = _management_model(
            name, scenario, compliance, unsuitable, model.output_fields,
            query=query, expected_outputs=expected_outputs, gaps=gaps,
            evidence_cards=evidence_cards,
        )
        demand_context = _demand_context(pr)
        if demand_context:
            business = demand_context + business
            technical = demand_context + technical
            management = demand_context + management

        return {
            "business": business,
            "technical": technical,
            "management": management,
        }

    @staticmethod
    def generate_composition_explanations(
        composition: RecommendCompositionResponse,
        parse_result: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """
        Generate three-mode explanations for a composition plan.

        Returns:
            {"business": "...", "technical": "...", "management": "..."}
        """
        scenario = (parse_result or {}).get("business_scenario", "") or composition.scenario
        name = composition.composition_name
        nodes = composition.nodes
        io = composition.io_compatibility

        business = _business_composition(name, scenario, nodes)
        technical = _technical_composition(name, nodes, io)
        management = _management_composition(name, scenario, nodes, io)

        return {
            "business": business,
            "technical": technical,
            "management": management,
        }

    def generate_recommendation_reason(
        self,
        model: dict[str, Any],
        parse_result: dict[str, Any],
        fallback_reason: str,
    ) -> dict[str, str]:
        """Generate an LLM recommendation reason using only supplied model facts."""
        if not getattr(self.llm, "available", False):
            return {"reason": fallback_reason, "source": "rule", "trace_id": ""}

        payload = self._build_model_payload(model, parse_result)
        system_prompt = self._load_prompt()
        result = self.llm.chat_json(system_prompt, json.dumps(payload, ensure_ascii=False), temperature=0.2)
        trace_id = getattr(self.llm, "last_trace_id", "")
        if not result:
            return {"reason": fallback_reason, "source": "fallback", "trace_id": trace_id}

        reason = str(result.get("recommendation_reason", "")).strip()
        if not self._valid_reason(reason, model):
            return {"reason": fallback_reason, "source": "fallback", "trace_id": trace_id}
        return {"reason": reason[:180], "source": "llm", "trace_id": trace_id}

    def _build_model_payload(self, model: dict[str, Any], parse_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "demand": {
                "raw_text": parse_result.get("raw_text", ""),
                "intent": parse_result.get("intent", ""),
                "business_scenario": parse_result.get("business_scenario", ""),
                "customer_segment": parse_result.get("customer_segment", []),
                "expected_outputs": parse_result.get("expected_outputs", []),
                "data_conditions": parse_result.get("data_conditions", []),
                "tags": parse_result.get("tags", []),
            },
            "model": {
                "model_id": model.get("model_id", ""),
                "model_name": model.get("model_name", ""),
                "domain": model.get("domain", ""),
                "business_scenario": model.get("business_scenario", []),
                "model_capability": model.get("model_capability", []),
                "input_fields_required": model.get("input_fields_required", []),
                "output_fields": model.get("output_fields", []),
                "applicable_conditions": model.get("applicable_conditions", ""),
                "unsuitable_conditions": model.get("unsuitable_conditions", ""),
                "compliance_boundary": model.get("compliance_boundary", ""),
                "tags": model.get("tags", []),
            },
        }

    def _load_prompt(self) -> str:
        try:
            return RECOMMENDATION_EXPLANATION_PROMPT.read_text(encoding="utf-8")
        except OSError:
            return "You explain banking model recommendations. Output only JSON."

    def _valid_reason(self, reason: str, model: dict[str, Any]) -> bool:
        if not reason or len(reason) > 220:
            return False
        prohibited = (
            r"(?:综合|推荐|匹配|内部|结构化|图谱|检索|LLM)\s*(?:得分|评分|分数)\s*[:：=]?\s*\d",
            r"\b(?:AUC|KS|Recall|Precision|F1|MAPE)\s*[:：=]\s*\d",
            r"置信度\s*[:：=]?\s*\d+(?:\.\d+)?%",
            r"(?:准确率|召回率|覆盖率|提升率|匹配率|相似度|总分)\s*[:：=]?\s*\d+(?:\.\d+)?%?",
        )
        if any(re.search(pattern, reason, flags=re.IGNORECASE) for pattern in prohibited):
            return False
        factual_terms = [
            str(model.get("model_name", "")),
            str(model.get("model_id", "")),
            *[str(item) for item in model.get("model_capability", [])],
            *[str(item) for item in model.get("input_fields_required", [])],
            *[str(item) for item in model.get("output_fields", [])],
        ]
        return any(term and term in reason for term in factual_terms)


# ─── Model explanation templates ───────────────────────────────

def _fmt_items(items: list[str], limit: int = 5) -> str:
    return "、".join(str(item) for item in items[:limit] if str(item).strip())


def _demand_context(parse_result: dict[str, Any]) -> str:
    scenario = str(parse_result.get("business_scenario") or "").strip()
    outputs = parse_result.get("expected_outputs") or []
    data_conditions = parse_result.get("data_conditions") or []
    tag_names = parse_result.get("tag_names") or []
    tags = parse_result.get("tags") or []
    focus_items = outputs or tag_names or tags
    parts: list[str] = []
    if scenario:
        parts.append(f"用户场景：{scenario}。")
    focus = _fmt_items([str(item) for item in focus_items], limit=6)
    if focus:
        parts.append(f"用户关注：{focus}。")
    data = _fmt_items([str(item) for item in data_conditions], limit=6)
    if data:
        parts.append(f"用户已说明的数据条件：{data}。")
    return "".join(parts)


# ─── Demand-model match gap detection ───────────────────────────

# Severe scenario conflict keyword pairs:
# (query_keywords, model_keywords, query_label, model_label)
_CONFLICT_PAIRS: list[tuple[list[str], list[str], str, str]] = [
    (
        ["信用卡", "个人逾期", "零售逾期", "个人客户逾期", "个人消费", "个人客户"],
        ["对公", "企业贷款", "公司贷款"],
        "个人信贷",
        "对公贷款",
    ),
    (
        ["理财", "产品响应", "营销响应", "响应推荐", "理财产品"],
        ["风险准入", "准入评分", "风控准入", "信贷准入", "普惠小微准入"],
        "理财产品营销响应",
        "风险准入",
    ),
    (
        ["客流", "排班", "网点客流", "客流趋势", "客流预测"],
        ["成本优化", "成本分析", "运营成本"],
        "客流预测与排班",
        "运营成本优化",
    ),
    (
        ["反洗钱", "洗钱", "可疑交易", "异常行为检测", "交易流水异常"],
        ["准入评分", "农户", "小额贷款准入", "贷前准入"],
        "反洗钱监测",
        "贷款准入评分",
    ),
    (
        ["欺诈识别", "反欺诈", "骗贷", "欺诈申请", "欺诈风险"],
        ["准入评分", "信用评分", "准入"],
        "欺诈识别",
        "准入评分",
    ),
    (
        ["流失", "挽留", "高价值客户流失", "客户流失"],
        ["沉睡", "唤醒", "睡眠客户"],
        "客户流失预测与挽留",
        "沉睡客户唤醒",
    ),
]


def _detect_severe_conflict(query: str, model_name: str, model_boundary: str) -> str | None:
    """Detect severe scenario conflict between user query and model."""
    query_lower = query.lower()
    model_text = (model_name + " " + model_boundary).lower()

    for query_kws, model_kws, query_label, model_label in _CONFLICT_PAIRS:
        query_hit = any(kw.lower() in query_lower for kw in query_kws)
        model_hit = any(kw.lower() in model_text for kw in model_kws)
        if query_hit and model_hit:
            return (
                f"注意：您的需求侧重于「{query_label}」，"
                f"而该模型主要面向「{model_label}」场景，"
                f"两者存在偏差，请确认该模型是否真正适用于您的业务需求。"
            )
    return None


def _detect_match_gaps(
    query: str,
    model: RecommendedModel,
    expected_outputs: list[str],
) -> list[str]:
    """Detect gaps between user demand and model capabilities."""
    gaps: list[str] = []
    sb = model.score_breakdown

    # 1. Severe scenario conflict (keyword-level)
    conflict = _detect_severe_conflict(query, model.model_name, model.applicable_boundary)
    if conflict:
        gaps.append(conflict)

    # 2. Low scenario match score
    if sb.scenario_match < 60:
        gaps.append(
            "该模型与当前场景的匹配信号较弱，"
            "其核心场景与您提出的需求可能存在偏差，建议确认是否适用。"
        )

    # 3. Missing expected outputs
    if expected_outputs:
        model_outputs_lower = {o.lower() for o in model.output_fields}
        missing_outputs = [
            o for o in expected_outputs
            if not any(o.lower() in mo or mo in o.lower() for mo in model_outputs_lower)
        ]
        if missing_outputs:
            gaps.append(f"该模型不直接提供您所需的输出：{_fmt_items(missing_outputs)}。")

    # 4. Low data match score
    if sb.data_match < 40:
        gaps.append(
            "该模型所需数据与您当前提供的数据条件匹配度较低，"
            "需补充相关数据后方可使用。"
        )

    # 5. Low customer match score
    if sb.customer_match < 40:
        gaps.append(
            "该模型的目标客群与您提出的客群匹配度较低，"
            "请确认客群是否一致。"
        )

    return gaps


# ─── Model explanation templates ───────────────────────────────

def _business_model(
    name: str,
    scenario: str,
    sb: ScoreBreakdown,
    boundary: str,
    required_data: list[str],
    missing_data: list[str],
    output_fields: list[str],
    compliance: str,
    query: str = "",
    expected_outputs: list[str] | None = None,
    gaps: list[str] | None = None,
    evidence_cards: list[EvidenceCard] | None = None,
    unsuitable: str = "",
) -> str:
    """Generate business-oriented explanation."""
    parts = [
        f"推荐模型《{name}》可覆盖“{scenario}”场景的核心需求。",
    ]

    # 需求匹配差距提示（诚实指出不匹配）
    if gaps:
        for g in gaps:
            parts.append(g)

    strong: list[str] = []
    if sb.scenario_match >= 80:
        strong.append("场景匹配")
    if sb.customer_match >= 80:
        strong.append("客群匹配")
    if sb.data_match >= 70:
        strong.append("数据条件匹配")
    if sb.output_match >= 80:
        strong.append("输出结果匹配")
    if sb.graph_path_match >= 80:
        strong.append("知识图谱路径匹配")
    if sb.field_compatibility >= 80:
        strong.append("字段兼容")
    if strong:
        parts.append("优势维度包括：" + "、".join(strong) + "。")
    else:
        parts.append("该模型能覆盖当前需求的核心方向，建议补充更明确的数据条件后再做最终选型。")
    outputs = _fmt_items(output_fields)
    if outputs:
        parts.append(f"可输出：{outputs}。")
    data = _fmt_items(required_data)
    if data:
        parts.append(f"主要依赖数据：{data}。")
    missing = _fmt_items(missing_data)
    if missing:
        parts.append(f"待补充或确认的数据：{missing}。")
    if boundary:
        parts.append(f"适用边界：{boundary}")
    if unsuitable:
        parts.append(f"不适用场景：{unsuitable}")
    if compliance:
        parts.append(f"合规与人工审核提示：{compliance}")
    else:
        parts.append("合规与人工审核提示：推荐结果仅作辅助，落地前需按行内制度完成授权、复核和审批。")

    # 证据引用
    if evidence_cards:
        for card in evidence_cards[:3]:
            if card.evidence_type == "性能指标" and card.content:
                parts.append(f"性能参考：{card.content}。")
                break

    return "".join(parts)


def _technical_model(
    name: str,
    model_id: str,
    sb: ScoreBreakdown,
    boundary: str,
    required_data: list[str],
    missing_data: list[str],
    output_fields: list[str],
    query: str = "",
    expected_outputs: list[str] | None = None,
    gaps: list[str] | None = None,
    evidence_cards: list[EvidenceCard] | None = None,
    compliance: str = "",
    unsuitable: str = "",
) -> str:
    """Generate technical-oriented explanation."""
    parts = [
        f"模型标识：{model_id}（{name}）\n",
        "排序依据覆盖场景、客群、数据、输出、知识图谱路径、字段兼容、性能、落地与合规等维度。\n",
        "页面展示模型事实字段和证据卡；内部排序信号仅用于候选排序，不替代人工评审。\n",
    ]

    # 需求匹配差距提示
    if gaps:
        parts.append("需求匹配差距：\n")
        for g in gaps:
            parts.append(f"  - {g}\n")

    data = _fmt_items(required_data, limit=8)
    if data:
        parts.append(f"必需输入字段：{data}\n")
    missing = _fmt_items(missing_data, limit=8)
    if missing:
        parts.append(f"当前缺口字段：{missing}\n")
    outputs = _fmt_items(output_fields, limit=8)
    if outputs:
        parts.append(f"输出字段：{outputs}\n")
    if boundary:
        parts.append(f"适用条件：{boundary}\n")
    if unsuitable:
        parts.append(f"不适用条件：{unsuitable}\n")

    # 合规提示
    if compliance:
        parts.append(f"合规提示：{compliance}\n")
    else:
        parts.append("合规提示：推荐结果仅作辅助，落地前需按行内制度完成授权、复核和审批。\n")

    # 证据引用
    if evidence_cards:
        parts.append("证据卡：\n")
        for card in evidence_cards[:3]:
            if card.content:
                parts.append(f"  [{card.evidence_type}] {card.content}\n")

    return "".join(parts)


def _management_model(
    name: str,
    scenario: str,
    compliance: str,
    unsuitable: str,
    output_fields: list[str],
    query: str = "",
    expected_outputs: list[str] | None = None,
    gaps: list[str] | None = None,
    evidence_cards: list[EvidenceCard] | None = None,
) -> str:
    """Generate management-oriented explanation."""
    parts = [
        f"决策建议：在“{scenario}”场景中，可优先评估部署《{name}》。\n"
    ]

    # 需求匹配差距提示
    if gaps:
        parts.append("需求匹配提示：\n")
        for g in gaps:
            parts.append(f"  - {g}\n")

    outputs = _fmt_items(output_fields)
    if outputs:
        parts.append(f"业务可获得的主要结果包括：{outputs}。\n")
    if compliance:
        parts.append(f"合规提示：{compliance}\n")
    if unsuitable:
        parts.append(f"慎用场景：{unsuitable}\n")

    # 证据引用
    if evidence_cards:
        for card in evidence_cards[:2]:
            if card.evidence_type == "性能指标" and card.content:
                parts.append(f"性能参考：{card.content}。\n")
                break

    parts.append(
        "建议结合业务专家经验、数据可得性和人工审核结论使用；模型推荐结果仅作辅助，最终决策需由有权审批人员确认。"
    )
    return "".join(parts)


# ─── Composition explanation templates ─────────────────────────

def _business_composition(name: str, scenario: str,
                          nodes: list[CompositionNode]) -> str:
    """Generate business-oriented composition explanation."""
    steps = [
        f"第{n.step_order}步：{n.node_explanation}（使用 {n.model_name}）"
        for n in sorted(nodes, key=lambda x: x.step_order)
    ]
    parts = [
        f"组合方案《{name}》面向“{scenario}”场景设计。\n",
        "业务流程：\n",
    ]
    for step in steps:
        parts.append(f"  - {step}\n")
    parts.append(
        "该组合覆盖从数据输入到结果输出的主要业务环节，各节点模型已完成适配度和 IO 兼容性评估。"
    )
    return "".join(parts)


def _technical_composition(name: str, nodes: list[CompositionNode],
                           io: Any) -> str:
    """Generate technical-oriented composition explanation."""
    io_rate = io.compatibility_rate * 100 if io else 0
    parts = [
        f"组合方案：{name}\n",
        f"节点数量：{len(nodes)} | IO 兼容率：{io_rate:.0f}%\n\n",
        "节点详情：\n",
    ]
    for n in sorted(nodes, key=lambda x: x.step_order):
        parts.append(
            f"  [{n.step_order}] {n.capability}\n"
            f"      模型：{n.model_name}\n"
            f"      输入：{'、'.join(n.input_requirements[:5])}\n"
            f"      输出：{'、'.join(n.output_fields[:5])}\n"
        )
    return "".join(parts)


def _management_composition(name: str, scenario: str,
                            nodes: list[CompositionNode], io: Any) -> str:
    """Generate management-oriented composition explanation."""
    node_count = len(nodes)
    io_rate = io.compatibility_rate * 100 if io else 0
    parts = [
        "管理摘要：\n",
        f"  组合方案《{name}》适用于“{scenario}”场景。\n",
        f"  节点数：{node_count} | IO 兼容率：{io_rate:.0f}%\n\n",
        "实施建议：\n",
        "  1. 建议先部署上游节点模型，验证数据链路后再扩展下游节点。\n",
        "  2. 各节点可采用增量上线方式，降低一次性投入风险。\n",
        "  3. 建议设置监控指标，持续跟踪各节点的业务效果和合规表现。\n\n",
        "风险提示：\n",
    ]
    if io and io.failed > 0:
        parts.append(f"  - 存在 {io.failed} 个 IO 兼容失败问题，需要补充数据转换或字段映射。\n")
    if io and io.partial > 0:
        parts.append(f"  - 存在 {io.partial} 个部分兼容问题，建议补充数据字段或人工确认。\n")
    if not io or (io.failed == 0 and io.partial == 0):
        parts.append("  - 当前未发现明确的 IO 阻断问题，仍需在真实数据接入前做人工复核。\n")
    return "".join(parts)
