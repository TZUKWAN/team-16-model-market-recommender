"""
demand_parser.py — Natural language demand parsing engine.

Rule-based intent/domain identification, slot extraction,
tag normalization, confidence scoring, clarification generation.
Runs without any LLM. Falls back gracefully on ambiguous input.

When LLM is available (LLM_API_KEY set), uses LLM for better accuracy.
"""

from __future__ import annotations
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.schemas.demand import ClarificationQuestion, ParseDemandResponse
from app.services.data_loader import (
    load_tags, build_synonym_map, get_tag_key_to_name,
)
from app.services.llm_client import get_llm_client
from app.repositories.model_asset_repository import get_model_asset_repository

logger = logging.getLogger(__name__)
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# ─── Keyword patterns ───────────────────────────────────────────

_INTENT_PATTERNS: dict[str, list[str]] = {
    "customer_marketing": [
        "营销", "获客", "拉新", "转化", "推荐", "名单", "促销",
        "响应", "交叉销售", "唤醒", "留存", "活跃", "偏好",
    ],
    "credit_risk": [
        "风控", "风险", "欺诈", "逾期", "违约", "坏账", "不良",
        "准入", "评分", "额度", "贷前", "贷中", "贷后", "预警",
        "催收", "反欺诈", "信用", "评级", "损失",
    ],
    "operation_management": [
        "运营", "网点", "客流", "排班", "效率", "流程", "成本",
        "绩效", "管理", "投诉", "服务", "异常", "对账",
    ],
}

_DOMAIN_MAP: dict[str, str] = {
    "customer_marketing": "客户营销",
    "credit_risk": "信贷风控",
    "operation_management": "运营管理",
}

_STAGE_PATTERNS: dict[str, list[str]] = {
    "marketing": ["营销", "获客", "推广", "触达"],
    "pre_loan": ["贷前", "准入", "申请", "审批", "首贷"],
    "in_loan": ["贷中", "放款", "交易", "在贷"],
    "post_loan": ["贷后", "预警", "催收", "逾期", "检查"],
}

_CUSTOMER_PATTERNS: dict[str, list[str]] = {
    "县域新客": ["县域新客", "新客", "县域", "县城"],
    "农户": ["农户", "农民", "农村", "农业", "种植", "养殖", "涉农"],
    "小微企业": ["小微", "中小企业", "个体户", "工商户"],
    "对公客户": ["对公", "企业", "公司", "集团"],
    "个人客户": ["个人", "零售", "消费者", "个贷"],
    "存量客户": ["存量", "老客", "已有客户", "存续"],
    "高价值客户": ["高价值", "VIP", "高端", "财富", "贵宾"],
}

_PRODUCT_PATTERNS: dict[str, list[str]] = {
    "首贷": ["首贷", "首次贷款", "首笔"],
    "小额贷款": ["小额", "微贷", "小额信贷"],
    "涉农贷款": ["涉农", "三农", "农业贷款", "农贷"],
    "对公贷款": ["对公贷款", "企业贷款", "公司贷款"],
    "消费贷": ["消费贷", "消费贷款", "个人消费"],
    "信用卡": ["信用卡", "贷记卡", "分期"],
}

_RISK_PATTERNS: dict[str, list[str]] = {
    "欺诈风险": ["欺诈", "诈骗", "骗贷", "虚假", "冒名"],
    "信用风险": ["信用", "违约", "坏账", "不良", "快坏账"],
    "逾期风险": ["逾期", "欠款", "拖欠", "不还"],
    "操作风险": ["操作", "内控", "合规", "内部"],
}

_OUTPUT_PATTERNS: dict[str, list[str]] = {
    "营销名单": ["名单", "营销清单", "目标客户"],
    "转化概率": ["转化概率", "转化率", "响应概率", "容易转化"],
    "客户排序": ["排序", "优先级", "排名", "客户排序"],
    "风险评分": ["评分", "风险评分", "风险分数", "打分"],
    "风险等级": ["等级", "风险等级", "评级", "分层"],
    "欺诈评分": ["欺诈评分", "欺诈分数"],
    "额度建议": ["额度", "额度建议", "授信", "贷款额度"],
    "预警名单": ["预警名单", "预警", "预警清单"],
    "逾期概率": ["逾期概率", "违约概率"],
}

_DATA_PATTERNS: dict[str, list[str]] = {
    "客户画像": ["画像", "基本信息", "个人资料", "客户信息"],
    "交易流水": ["流水", "交易", "收支"],
    "征信报告": ["征信", "信用报告"],
    "还款记录": ["还款", "还款记录"],
    "营销触达记录": ["营销记录", "触达", "响应记录"],
}

# ─── Helpers ────────────────────────────────────────────────────

def _match_keywords(text: str, patterns: list[str]) -> float:
    """Score how well text matches a list of keyword patterns (0-1)."""
    text_lower = text.lower()
    matches = sum(1 for kw in patterns if kw.lower() in text_lower)
    if not patterns or matches == 0:
        return 0.0
    return min(1.0, matches / max(1, len(patterns)) * 1.5)


def _extract_matches(text: str, pattern_map: dict[str, list[str]]) -> dict[str, float]:
    """Extract matching entries and their confidence scores."""
    result: dict[str, float] = {}
    text_lower = text.lower()
    for key, keywords in pattern_map.items():
        confidence = _match_keywords(text_lower, keywords)
        if confidence > 0:
            result[key] = confidence
    return result


def _normalize_text(text: str) -> str:
    """Normalize query text for processing."""
    text = text.strip()
    text = re.sub(r'[，。！？、；：""\'\'（）【】《》\s]+', " ", text)
    return text


def _tag_keys_str() -> str:
    """Build a comma-separated list of all valid tag keys."""
    try:
        from app.services.data_loader import load_tags
        tags_data = load_tags()
        keys = []
        for tag in tags_data.get("tags", []):
            keys.append(tag.get("key", ""))
        return ",".join(keys) if keys else "credit_risk,customer_marketing"
    except Exception:
        return "credit_risk,customer_marketing,operation_management,pre_loan,post_loan"


# ─── DemandParser ──────────────────────────────────────────────

class DemandParser:
    """
    Rule-based demand parser. No LLM required.
    Uses keyword matching, synonym resolution, and heuristic scoring.
    """

    def __init__(self):
        self.tags_data = load_tags()
        self.synonym_map = build_synonym_map(self.tags_data)
        self.tag_key_to_name = get_tag_key_to_name(self.tags_data)
        self.valid_tag_keys = set(self.tag_key_to_name.keys())
        self.models = get_model_asset_repository().list_models()
        self.llm = get_llm_client()
        self.synonyms_config = self._load_synonyms()

    def _load_synonyms(self) -> dict[str, list[str]]:
        """Load synonym mappings from config file. Returns empty dict on failure."""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "data", "config", "synonyms.json"
        )
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load synonyms config: {e}")
            return {}

    def _expand_with_synonyms(self, text: str) -> str:
        """Expand text by appending synonyms found in the text.

        E.g., '逾期贷款' with synonym '逾期'→['违约','不良']
        returns '逾期贷款 违约 不良' to help keyword matching.
        """
        if not self.synonyms_config:
            return text
        expanded = text
        for key, synonyms in self.synonyms_config.items():
            if key in text:
                for syn in synonyms:
                    if syn not in expanded:
                        expanded += " " + syn
        return expanded

    def _to_tag_key(self, value: str) -> str | None:
        if not value:
            return None
        value = str(value).strip()
        if value in self.valid_tag_keys:
            return value
        if value in self.synonym_map:
            return self.synonym_map[value]
        for key, name in self.tag_key_to_name.items():
            if value == name:
                return key
        return None

    def _tag_names(self, tag_keys: list[str]) -> list[str]:
        return [self.tag_key_to_name.get(k, k) for k in tag_keys]

    def _prompt_text(self, filename: str, fallback: str) -> str:
        path = PROMPT_DIR / filename
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return fallback

    def _as_str_list(self, value: Any, max_items: int = 8) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = [value]
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = [str(value)]
        items: list[str] = []
        for item in raw_items:
            text = str(item).strip()
            if text and text not in items:
                items.append(text[:80])
            if len(items) >= max_items:
                break
        return items

    def _confidence(self, value: Any, default: float = 0.85) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = default
        return max(0.0, min(1.0, score))

    def parse(self, raw_text: str, context: dict[str, Any] | None = None, use_llm: bool | None = None) -> ParseDemandResponse:
        """Parse a natural language demand into structured result.
        Uses LLM when available, falls back to rule-based parsing.

        ``use_llm`` forces the parse path: ``None`` keeps legacy behavior
        (LLM when configured), ``False`` forces rule-only (used by ablation
        and as a deterministic fallback), ``True`` forces an LLM attempt.
        """
        llm_active = self.llm.available if use_llm is None else (use_llm and self.llm.available)
        # Extract prior-turn Q&A history from context so the LLM sees the full
        # multi-turn conversation rather than re-parsing each turn in isolation.
        history = self._extract_history(context)
        if llm_active:
            llm_result = self._parse_with_llm(raw_text, history=history)
            if llm_result is not None:
                return llm_result
            fallback = self._parse_rules(raw_text)
            fallback.parse_source = "hybrid_fallback"
            fallback.llm_enabled = True
            fallback.llm_trace_id = getattr(self.llm, "last_trace_id", "")
            fallback.llm_fallback_reason = str(
                getattr(self.llm, "last_call_status", {}).get("reason") or "invalid_llm_result"
            )[:80]
            return fallback
        result = self._parse_rules(raw_text)
        result.llm_enabled = llm_active
        return result

    @staticmethod
    def _extract_history(context: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Pull the flattened Q&A history out of the parse context.

        The API layer stores the conversation's accumulated Q&A under
        ``context["history"]`` (a list of {question, answer, slot}). Older
        callers may still pass ``context["clarification_answers"]``; we fold
        those in too for backward compatibility.
        """
        if not context:
            return []
        history: list[dict[str, Any]] = []
        for item in context.get("history", []) or []:
            if isinstance(item, dict):
                history.append({
                    "question": item.get("question", item.get("question_text", "")),
                    "answer": item.get("answer", item.get("user_answer", "")),
                    "slot": item.get("slot", ""),
                })
        # Backward-compat: legacy clarification_answers shape.
        for item in context.get("clarification_answers", []) or []:
            if isinstance(item, dict):
                history.append({
                    "question": item.get("question_text", ""),
                    "answer": item.get("user_answer", ""),
                    "slot": item.get("slot", ""),
                })
        return [h for h in history if h.get("answer")]

    def _parse_rules(self, raw_text: str) -> ParseDemandResponse:
        """Rule-based parsing (original logic)."""
        text = _normalize_text(raw_text)

        # 1. Intent / domain identification
        intent, intent_conf = self._identify_intent(text)

        # 2. Slot extraction
        scenario, stage, customers, products, risks, outputs, constraints, data_conds = \
            self._extract_slots(text, intent)

        # 3. Tag normalization & confidence
        tags, tag_conf = self._normalize_tags(text, intent, customers, products, risks, outputs)

        # 3.5 Enrich tags with inference rules
        self._enrich_tags(tags, set(tags), intent, text,
                         customers, stage, outputs, risks, products)

        # 4. Structured filters
        filters = self._build_filters(intent, customers, products, risks)

        # 5. Detect missing slots
        missing, need_clarification, questions = self._detect_missing(
            scenario, stage, customers, outputs, data_conds, intent, text
        )

        # 6. Translation & summary
        translation = self._generate_translation(intent, scenario, tags)
        summary = self._generate_summary(intent, scenario, customers, outputs, data_conds)

        # Normalize query
        normalized = self._normalize_query(raw_text, intent, scenario)

        return ParseDemandResponse(
            raw_text=raw_text,
            normalized_query=normalized,
            parse_source="rule",
            llm_enabled=self.llm.available,
            intent=intent,
            intent_confidence=round(intent_conf, 2),
            domain=_DOMAIN_MAP.get(intent, "未识别"),
            business_scenario=scenario,
            business_stage=stage,
            customer_segment=customers,
            product_type=products,
            risk_type=risks,
            expected_outputs=outputs,
            constraints=constraints,
            data_conditions=data_conds,
            tags=tags,
            tag_names=self._tag_names(tags),
            tag_confidence={t: round(tag_conf.get(t, 0.5), 2) for t in tags},
            missing_slots=missing,
            need_clarification=need_clarification,
            clarification_questions=self._build_clarification_questions(missing, questions),
            structured_filters=filters,
            business_to_model_translation=translation,
            user_confirmable_summary=summary,
        )

    def _identify_intent(self, text: str) -> tuple[str, float]:
        """Identify primary intent and confidence."""
        expanded_text = self._expand_with_synonyms(text)
        override = self._domain_override(expanded_text)
        if override:
            return override, 0.95

        scores: dict[str, float] = {}
        for intent, keywords in _INTENT_PATTERNS.items():
            scores[intent] = _match_keywords(expanded_text, keywords)

        if not scores or all(v == 0 for v in scores.values()):
            return "customer_marketing", 0.3

        best = max(scores, key=lambda k: scores[k])
        best_score = scores[best]
        # Check for mixed intents
        second_score = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0
        if best_score < 0.05:
            return "customer_marketing", 0.3

        # If two intents close, reduce confidence
        confidence = best_score
        if second_score > 0 and best_score - second_score < 0.15:
            confidence *= 0.85

        return best, min(confidence, 0.98)

    def _domain_override(self, text: str) -> str | None:
        """High-precision domain rules for official model-market scenarios."""
        if any(key in text for key in ["本次优先解决风险", "优先解决风险", "优先解决风控", "优先围绕风险"]):
            return "credit_risk"
        if any(key in text for key in ["本次优先解决营销", "优先解决营销", "优先围绕营销"]):
            return "customer_marketing"
        if any(key in text for key in ["本次优先解决运营", "优先解决运营", "优先围绕运营"]):
            return "operation_management"

        operation_patterns = [
            ["信贷从业"],
            ["信贷人员"],
            ["客户经理", "操作风险"],
            ["操作风险", "监测"],
            ["房地产", "压力测试"],
            ["压力测试", "房价"],
            ["房地产", "房价下跌"],
            ["抵押", "房价", "风险暴露"],
            ["综合评价", "产品"],
            ["指标", "加权", "星级"],
            ["指标评价"],
            ["星级评分"],
            ["贷款产品", "综合评价"],
            ["贷款产品", "评价"],
            ["产品评价"],
            ["产品集市"],
            ["贷款产品管理"],
            ["理财产品", "综合评价"],
            ["理财产品", "指标"],
            ["收单商户", "预授信"],
            ["收单商户", "价值分层"],
            ["收单商户", "授信额度"],
            ["商户", "推荐利率"],
            ["授信后", "未用信"],
            ["已授信", "未用信"],
            ["授信客户", "用信可能性"],
            ["授信客户", "一直不用"],
            ["额度", "一直不用"],
            ["未来可能用信"],
            ["消费贷额度", "不用"],
            ["用信概率"],
            ["审批通过", "迟迟不借款"],
            ["未来", "使用信用额度"],
            ["扬州", "重点企业"],
            ["扬州地区", "企业"],
            ["地方重点企业"],
            ["企业标签化"],
            ["营销意向标签"],
            ["开通", "手机银行"],
            ["办理", "手机银行"],
            ["签约手机银行"],
            ["手机银行新客拓展"],
            ["中介", "涉诈"],
            ["首期", "反欺诈"],
            ["个贷全流程"],
            ["风控中台"],
            ["零售业务", "反欺诈"],
            ["申请阶段", "涉诈"],
            ["坏样本", "反欺诈"],
        ]
        credit_patterns = [
            ["电信诈骗"],
            ["涉诈"],
            ["反诈"],
            ["非法集资"],
            ["对私账户", "风控"],
            ["账户交易", "诈骗"],
            ["交易行为", "反诈"],
            ["贷前", "反欺诈"],
            ["欺诈风险"],
            ["信用卡", "申请"],
            ["信用卡", "审批"],
            ["信用卡", "贷前"],
            ["信用卡", "征信"],
            ["信用卡", "欺诈"],
            ["信用卡", "风险"],
            ["信用卡", "额度管理"],
            ["申请评分", "信用卡"],
            ["房贷", "贷前"],
            ["房贷", "准入"],
            ["按揭", "准入"],
            ["按揭", "违约"],
            ["逾期", "催收"],
            ["不良率", "催收"],
            ["催收资源"],
            ["表现期", "后四类"],
            ["无法查征信"],
            ["中小微企业", "资金流", "信用信息"],
            ["收单商户", "异常交易"],
        ]
        marketing_patterns = [
            ["理财", "购买"],
            ["理财", "营销"],
            ["理财", "推荐"],
            ["理财", "响应"],
            ["理财", "产品匹配"],
            ["理财", "新客营销"],
            ["理财", "获客"],
            ["理财拓新"],
            ["财富", "推荐"],
            ["财富", "维稳"],
            ["财富管理", "产品匹配"],
            ["保险", "购买"],
            ["保险", "代销"],
            ["信用卡", "办理"],
            ["信用卡", "办卡"],
            ["信用卡", "拓展"],
            ["信用卡", "额度调整"],
            ["用卡频次", "额度"],
            ["信用卡", "分期意愿"],
            ["贷记卡", "账单分期"],
            ["账单", "办理分期"],
            ["固定额度", "调整"],
            ["调额"],
            ["流失", "挽留"],
            ["流失", "回捞"],
            ["留存", "营销"],
            ["提前预警", "精准维护"],
            ["客户", "结清", "流失"],
            ["小微", "流失预警"],
            ["贷款客户", "流失"],
            ["高价值客户", "流失"],
            ["存款流失"],
            ["AUM", "流失"],
            ["代发", "留存"],
            ["授信", "未用信"],
            ["未来可能用信"],
            ["房贷客户", "交叉销售"],
            ["房贷按揭客户", "新增借据"],
            ["低风险房贷", "贷款产品"],
            ["借记卡", "信用卡"],
            ["潜在办卡"],
            ["贷款中介"],
            ["收款次数异常", "账户"],
            ["收单业务", "流失"],
            ["商户", "办理意向"],
            ["长尾客户", "高价值"],
            ["AUM低于1万", "高价值"],
            ["他行有钱", "本行资产不高"],
            ["资产不高", "高潜力"],
            ["高净值", "存款流失"],
        ]

        for patterns, domain in [
            (operation_patterns, "operation_management"),
            (credit_patterns, "credit_risk"),
            (marketing_patterns, "customer_marketing"),
        ]:
            for group in patterns:
                if all(keyword in text for keyword in group):
                    return domain
        return None

    def _extract_slots(self, text: str, intent: str) -> tuple:
        """Extract all slots from text."""
        expanded = self._expand_with_synonyms(text)

        # Business scenario
        scenario = self._extract_business_scenario(expanded, intent)

        # Business stage
        stage_matches = _extract_matches(expanded, _STAGE_PATTERNS)
        stage = max(stage_matches, key=lambda k: stage_matches[k]) if stage_matches else ""
        # Map to display name
        stage_display_map = {
            "marketing": "营销", "pre_loan": "贷前",
            "in_loan": "贷中", "post_loan": "贷后",
        }
        stage = stage_display_map.get(stage, stage)

        # Customer segment
        customers = list(_extract_matches(expanded, _CUSTOMER_PATTERNS).keys())

        # Product type
        products = list(_extract_matches(expanded, _PRODUCT_PATTERNS).keys())

        # Risk type
        risks = list(_extract_matches(expanded, _RISK_PATTERNS).keys())

        # Expected outputs
        outputs = list(_extract_matches(expanded, _OUTPUT_PATTERNS).keys())

        # Constraints
        constraints: list[str] = []
        amount_match = re.search(r"(\d+)\s*[万亿万千]?\s*[元块]", text)
        if amount_match:
            constraints.append(f"贷款金额≤{amount_match.group(0)}")
        time_match = re.search(r"提前\s*(\d+)\s*天", text)
        if time_match:
            constraints.append(f"提前{time_match.group(1)}天预警")

        # Data conditions
        data_conds = list(_extract_matches(expanded, _DATA_PATTERNS).keys())

        # If intent is credit_risk and no risk type detected, add a default
        if intent == "credit_risk" and not risks:
            if "贷后" in text or "预警" in text:
                risks.append("逾期风险")

        return scenario, stage, customers, products, risks, outputs, constraints, data_conds

    def _extract_business_scenario(self, text: str, intent: str) -> str:
        """Extract business scenario based on text and intent."""
        scenarios = {
            "customer_marketing": [
                ("县域新客首贷营销", ["县域", "新客", "首贷"]),
                ("涉农营销", ["涉农", "农户", "三农"]),
                ("小微企业营销", ["小微", "企业", "普惠"]),
                ("存量客户经营", ["存量", "交叉", "留存"]),
                ("营销活动优化", ["营销", "响应", "活动"]),
                ("首贷营销", ["首贷", "白名单"]),
            ],
            "credit_risk": [
                ("农户小额贷款贷前准入", ["农户", "贷前", "准入", "小额"]),
                ("小微企业贷前准入", ["小微", "贷前", "准入", "企业"]),
                ("对公贷款贷后预警", ["对公", "贷后", "预警", "逾期"]),
                ("个人消费贷审批", ["消费贷", "个人", "申请"]),
                ("贷后管理", ["贷后", "管理", "检查"]),
                ("信用卡风险管理", ["信用卡", "分期"]),
            ],
            "operation_management": [
                ("网点运营", ["网点", "客流", "柜面"]),
                ("运营风控", ["运营", "异常", "风控"]),
                ("渠道运营", ["渠道", "手机银行", "线上"]),
                ("内控合规", ["合规", "内控", "审计"]),
            ],
        }

        intent_scenarios = scenarios.get(intent, [])
        best_match = ""
        best_score = 0
        for scenario_name, keywords in intent_scenarios:
            score = _match_keywords(text, keywords)
            if score > best_score:
                best_score = score
                best_match = scenario_name

        return best_match if best_match else self._fallback_scenario(intent, text)

    def _fallback_scenario(self, intent: str, text: str) -> str:
        """Generate a fallback scenario when keywords don't match."""
        domain = _DOMAIN_MAP.get(intent, "金融")
        # Try to extract some context
        words = [w for w in text.split() if len(w) > 1]
        context_words = words[:3] if words else []
        if context_words:
            return f"{domain}相关场景"
        return f"{domain}通用场景"

    def _normalize_tags(self, text: str, intent: str, customers: list[str],
                        products: list[str], risks: list[str],
                        outputs: list[str]) -> tuple[list[str], dict[str, float]]:
        """Normalize extracted info into standard tag keys with confidence."""
        tag_conf: dict[str, float] = {}

        def _add_tag(key: str, conf: float):
            if key and key in self.valid_tag_keys:
                tag_conf[key] = max(tag_conf.get(key, 0), round(min(conf, 0.99), 2))

        # From customer segments
        for c in customers:
            key = self._to_tag_key(c)
            if key:
                _add_tag(key, 0.8)
        # From product types
        for p in products:
            key = self._to_tag_key(p)
            if key:
                _add_tag(key, 0.8)
        # From risk types
        for r in risks:
            key = self._to_tag_key(r)
            if key:
                _add_tag(key, 0.85)
        # From expected outputs
        for o in outputs:
            key = self._to_tag_key(o)
            if key:
                _add_tag(key, 0.75)
        # Intent as domain tag
        if intent in self.valid_tag_keys:
            _add_tag(intent, 0.6)

        # Capability tags from keyword matching
        capability_keywords: dict[str, list[str]] = {
            "admission_scoring": ["能不能贷", "准入", "评分", "准入评分"],
            "anti_fraud": ["欺诈", "反欺诈", "骗贷"],
            "default_prediction": ["逾期", "违约", "逾期预测"],
            "early_warning": ["预警", "监测", "提前发现"],
            "amount_estimation": ["额度", "额度测算", "授信"],
            "conversion_prediction": ["转化", "容易转化", "转换"],
            "response_prediction": ["响应", "响应率"],
            "ranking": ["排序", "名单排序", "优先级"],
            "credit_rating": ["评级", "信用评级", "信用等级"],
            "customer_value": ["交叉", "交叉销售", "产品推荐"],
        }
        for tag_key, keywords in capability_keywords.items():
            score = _match_keywords(text, keywords)
            if score > 0:
                _add_tag(tag_key, score * 0.7)

        sorted_tags = sorted(tag_conf.items(), key=lambda x: -x[1])
        tags = [k for k, _ in sorted_tags]
        conf_dict = dict(sorted_tags)

        return tags, conf_dict

    def _build_filters(self, intent: str, customers: list[str],
                       products: list[str], risks: list[str]) -> dict[str, Any]:
        """Build structured filter dict."""
        filters: dict[str, Any] = {}
        if intent:
            filters["domain"] = intent
        if customers:
            filters["customer_type"] = customers[0]
        if products:
            filters["product_type"] = products[0]
        if risks:
            filters["risk_type"] = risks[0]
        return filters

    def _detect_missing(self, scenario: str, stage: str, customers: list[str],
                        outputs: list[str], data_conds: list[str],
                        intent: str, text: str) -> tuple[list[str], bool, list[str]]:
        """Detect missing slots and generate clarification questions."""
        missing: list[str] = []
        questions: list[str] = []

        if not scenario or scenario.endswith("通用场景") or scenario.endswith("相关场景"):
            missing.append("business_scenario")
            questions.append("请问您的业务具体属于哪个场景？例如：客户营销、贷前风控、贷后预警等")

        if not customers:
            missing.append("customer_segment")
            questions.append("请问您的目标客户群体是哪些？例如：农户、小微企业、对公客户、个人客户等")

        if not outputs:
            missing.append("expected_outputs")
            questions.append("请问您期望模型输出什么结果？例如：风险评分、转化概率、营销名单等")

        # Add data condition question if too few conditions
        if len(data_conds) < 2 and missing:
            if "数据" not in text and "data" not in text.lower():
                questions.append("请问您目前有哪些可用数据？例如：客户画像、交易流水、征信报告等")

        # Limit to 3 questions max
        questions = questions[:3]

        need_clarification = len(missing) > 0
        return missing, need_clarification, questions

    def _build_clarification_questions(
        self,
        missing_slots: list[str],
        questions: list[str],
    ) -> list[ClarificationQuestion]:
        """Convert question text into structured frontend-friendly objects."""
        option_map = {
            "business_scenario": ["客户营销", "贷前风控", "贷后预警", "运营管理"],
            "customer_segment": ["县域新客", "农户", "小微企业", "对公客户", "存量客户"],
            "expected_outputs": ["评分/概率", "名单/排序", "风险等级", "额度建议", "预警原因"],
            "data_conditions": ["客户画像", "交易流水", "征信报告", "营销历史", "运营日志"],
        }
        structured: list[ClarificationQuestion] = []
        for index, question in enumerate(questions[:3], start=1):
            slot = missing_slots[index - 1] if index - 1 < len(missing_slots) else "other"
            structured.append(
                ClarificationQuestion(
                    question_id=f"q{index}_{slot}",
                    question_text=question,
                    slot=slot,
                    options=option_map.get(slot, []),
                )
            )
        return structured

    def _generate_translation(self, intent: str, scenario: str, tags: list[str]) -> str:
        """Generate business-to-model translation text."""
        parts = []
        domain = _DOMAIN_MAP.get(intent, "金融")
        parts.append(f"该需求属于{domain}领域")
        if scenario:
            parts.append(f"的{scenario}场景")
        if tags:
            top_tags = tags[:4]
            parts.append(f"，可匹配{'、'.join(top_tags)}等模型能力")
        return "".join(parts)

    def _generate_summary(self, intent: str, scenario: str, customers: list[str],
                          outputs: list[str], data_conds: list[str]) -> str:
        """Generate a user-friendly summary."""
        parts: list[str] = []

        if scenario:
            parts.append(f"场景：{scenario}")
        if customers:
            parts.append(f"客群：{'、'.join(customers[:3])}")
        if outputs:
            parts.append(f"目标：{'、'.join(outputs[:3])}")
        if data_conds:
            parts.append(f"数据：{'、'.join(data_conds[:3])}")

        return " | ".join(parts) if parts else "已解析您的需求，请确认以下推荐结果。"

    def _normalize_query(self, raw_text: str, intent: str, scenario: str) -> str:
        """Generate a normalized version of the query."""
        text = _normalize_text(raw_text)
        # Keep the original but cleaned
        return text[:200]

    def _parse_with_llm(self, raw_text: str, history: list[dict[str, Any]] | None = None) -> ParseDemandResponse | None:
        """Use LLM for high-accuracy demand parsing.

        When ``history`` is provided (multi-turn clarification), the LLM sees
        the accumulated Q&A so it can refine the parse and avoid re-asking
        questions the user has already answered.
        """
        intent_keys = list(_INTENT_PATTERNS.keys())
        domain_names = {k: _DOMAIN_MAP.get(k, k) for k in intent_keys}

        system_base = self._prompt_text(
            "demand_parse_system.md",
            "You are a bank business requirement parser. Output only valid JSON.",
        )
        system = (
            f"{system_base}\n\n"
            f"Allowed intent keys: {intent_keys}\n"
            f"Domain mapping: {json.dumps(domain_names, ensure_ascii=False)}\n"
            f"Allowed tag keys: {_tag_keys_str()}"
        )

        history_block = ""
        if history:
            history_lines = "\n".join(
                f"  - 问：{h.get('question', '')}  答：{h.get('answer', '')}"
                for h in history
            )
            history_block = (
                f"\nPREVIOUS CLARIFICATION (已确认的多轮信息，请纳入本次解析，不要重复追问)：\n"
                f"{history_lines}\n"
            )

        user = (
            f"Parse this bank business requirement into structured JSON:\n"
            f"USER QUERY: {raw_text}\n"
            f"{history_block}\n"
            "Return JSON with these fields (keep business_scenario concise, under 20 chars):\n"
            '  "intent": one of the intent values above,\n'
            '  "intent_confidence": 0-1 float,\n'
            '  "business_scenario": string describing the specific business scenario,\n'
            '  "business_stage": pre_loan/in_loan/post_loan/marketing/空字符串,\n'
            '  "customer_segment": array of customer segment labels,\n'
            '  "product_type": array of product type labels,\n'
            '  "risk_type": array of risk type labels,\n'
            '  "expected_outputs": array of expected output descriptions,\n'
            '  "constraints": array of constraints,\n'
            '  "data_conditions": array of needed data fields,\n'
            f'  "tags": array of TAG KEYS ONLY from: {_tag_keys_str()}\n'
            '  "need_clarification": boolean,\n'
            '  "clarification_questions": array of 1-3 questions if needed,\n'
            '  "user_confirmable_summary": string summary for user confirmation\n'
        )

        result = self.llm.chat_json(
            system,
            user,
            prompt_version="demand-parser-v2",
            cache_context={"tag_taxonomy": _tag_keys_str()},
        )
        if not result:
            return None

        try:
            intent = result.get("intent", "customer_marketing")
            if intent not in intent_keys:
                rule_intent, _ = self._identify_intent(_normalize_text(raw_text))
                intent = rule_intent if rule_intent in intent_keys else "customer_marketing"
            intent_confidence = self._confidence(result.get("intent_confidence", 0.85))

            # Normalize tags: convert EVERYTHING to standard tag keys
            raw_tags = result.get("tags", [])
            normalized_tags: list[str] = []
            seen_keys: set[str] = set()
            for t in raw_tags:
                t_str = str(t).strip()
                key = self._to_tag_key(t_str)
                if key and key in self.valid_tag_keys and key not in seen_keys:
                    normalized_tags.append(key)
                    seen_keys.add(key)

            customer_segment = self._as_str_list(result.get("customer_segment", []))
            product_type = self._as_str_list(result.get("product_type", []))
            risk_type = self._as_str_list(result.get("risk_type", []))
            expected_outputs = self._as_str_list(result.get("expected_outputs", []))
            constraints = self._as_str_list(result.get("constraints", []))
            data_conditions = self._as_str_list(result.get("data_conditions", []))
            business_stage = str(result.get("business_stage", "")).strip()[:40]
            business_scenario = str(result.get("business_scenario", "")).strip()[:80]

            # Enrich tags with domain-inferred rules
            self._enrich_tags(normalized_tags, seen_keys, intent, raw_text,
                             customer_segment,
                             business_stage,
                             expected_outputs,
                             risk_type,
                             product_type)

            if not normalized_tags and intent in self.valid_tag_keys:
                normalized_tags.append(intent)

            tag_conf = {t: round(intent_confidence, 2) for t in normalized_tags}
            filters = self._build_filters(intent, customer_segment, product_type, risk_type)
            missing, need_clarification, rule_questions = self._detect_missing(
                business_scenario,
                business_stage,
                customer_segment,
                expected_outputs,
                data_conditions,
                intent,
                raw_text,
            )
            llm_questions = self._as_str_list(result.get("clarification_questions", []), max_items=3)
            need_clarification = bool(result.get("need_clarification", False)) or need_clarification
            questions = llm_questions or rule_questions
            trace_id = getattr(self.llm, "last_trace_id", "")

            return ParseDemandResponse(
                raw_text=raw_text,
                normalized_query=_normalize_text(raw_text),
                parse_source="llm",
                llm_enabled=True,
                llm_trace_id=trace_id,
                intent=intent,
                intent_confidence=round(intent_confidence, 2),
                domain=_DOMAIN_MAP.get(intent, "未识别"),
                business_scenario=business_scenario,
                business_stage=business_stage,
                customer_segment=customer_segment,
                product_type=product_type,
                risk_type=risk_type,
                expected_outputs=expected_outputs,
                constraints=constraints,
                data_conditions=data_conditions,
                tags=normalized_tags,
                tag_names=self._tag_names(normalized_tags),
                tag_confidence=tag_conf,
                missing_slots=missing,
                need_clarification=need_clarification,
                clarification_questions=self._build_clarification_questions(missing, questions),
                structured_filters=filters,
                business_to_model_translation=f"该需求属于{_DOMAIN_MAP.get(intent, '金融')}领域",
                user_confirmable_summary=str(result.get("user_confirmable_summary", "")),
            )
        except Exception as e:
            logger.warning(f"LLM parse result malformed: {e}")
            return None

    def _enrich_tags(self, tags: list[str], seen: set[str], intent: str,
                     raw_text: str, customers: list[str], stage: str,
                     outputs: list[str], risks: list[str],
                     products: list[str] | None = None):
        """Infer additional tags from domain, stage, customer, product, capability hints.

        add_tag() validates against valid_tag_keys, so keys that don't exist
        in the taxonomy are silently skipped (per plan spec).
        """

        def add_tag(key: str):
            if key and key in self.valid_tag_keys and key not in seen:
                tags.append(key)
                seen.add(key)

        # Domain tag
        add_tag(intent)

        # Business stage
        stage_text = f"{stage} {raw_text}"
        if "贷前" in stage_text or "pre_loan" in stage_text:
            add_tag("pre_loan")
        if "贷中" in stage_text or "in_loan" in stage_text:
            add_tag("in_loan")
        if "贷后" in stage_text or "post_loan" in stage_text:
            add_tag("post_loan")
        if "营销" in stage_text or "marketing" in stage_text:
            add_tag("pre_marketing")
            add_tag("in_marketing")
            add_tag("marketing")
        if "日常运营" in stage_text or "网点" in stage_text:
            add_tag("daily_operation")
        if "绩效" in stage_text:
            add_tag("performance_analysis")
        if any(k in stage_text for k in ["资源", "排班", "调配"]):
            add_tag("resource_planning")
        if any(k in stage_text for k in ["合规", "监管"]):
            add_tag("compliance")

        # Customer segment
        text = raw_text + " " + " ".join(map(str, customers))
        if any(k in text for k in ["农户", "三农", "农民", "农村", "农业"]):
            add_tag("farmer")
        if any(k in text for k in ["县域"]):
            add_tag("rural_area")
            add_tag("county_new_customer")
        if any(k in text for k in ["小微", "个体工商"]):
            add_tag("small_micro_enterprise")
        if any(k in text for k in ["对公", "企业", "公司"]):
            add_tag("corporate")
        if any(k in text for k in ["个人", "零售"]):
            add_tag("individual")
        if any(k in text for k in ["存量", "老客"]):
            add_tag("existing_customer")
        if any(k in text for k in ["沉睡", "睡眠"]):
            add_tag("dormant_customer")
        if any(k in text for k in ["流失"]):
            add_tag("churned_customer")
            add_tag("existing_customer")
        if any(k in text for k in ["新客", "新客户"]):
            add_tag("new_customer")

        # Product type
        product_text = raw_text + " " + " ".join(map(str, products or []))
        if any(k in product_text for k in ["小额"]):
            add_tag("small_loan")
        if any(k in product_text for k in ["涉农", "农贷", "农业贷款"]):
            add_tag("agricultural_loan")
            add_tag("farmer")
        if any(k in product_text for k in ["对公贷款", "企业贷款"]):
            add_tag("corporate_loan")
            add_tag("corporate")
        if any(k in product_text for k in ["消费贷"]):
            add_tag("consumer_loan")
        if any(k in product_text for k in ["信用卡"]):
            add_tag("credit_card")
        if any(k in product_text for k in ["存款"]):
            add_tag("deposit")
        if any(k in product_text for k in ["首贷", "首次贷款", "首笔"]):
            add_tag("first_loan")

        # Capability inference
        cap_text = (
            raw_text + " "
            + " ".join(map(str, outputs)) + " "
            + " ".join(map(str, risks))
        )

        if any(k in cap_text for k in ["反欺诈", "欺诈", "骗贷", "身份异常"]):
            add_tag("anti_fraud")

        if any(k in cap_text for k in ["准入", "能不能贷", "审批"]):
            add_tag("admission_scoring")

        if any(k in cap_text for k in ["额度", "授信"]):
            add_tag("amount_calculation")
            add_tag("amount_estimation")

        if any(k in cap_text for k in ["逾期", "违约", "PD"]):
            add_tag("default_prediction")

        if any(k in cap_text for k in ["预警", "提前发现", "报警"]):
            add_tag("early_warning")

        if any(k in cap_text for k in ["异常", "异常识别"]):
            add_tag("anomaly_detection")

        if any(k in cap_text for k in ["反洗钱", "可疑交易", "大额交易"]):
            add_tag("anti_money_laundering")
            add_tag("compliance_check")
            add_tag("anomaly_detection")
            add_tag("anti_fraud")

        if any(k in cap_text for k in ["合规", "监管", "制度", "报表"]):
            add_tag("compliance_check")
            add_tag("compliance")

        if any(k in cap_text for k in ["流失", "挽留"]):
            add_tag("churn_prediction")
            add_tag("existing_customer")

        if any(k in cap_text for k in ["响应", "响应率"]):
            add_tag("response_prediction")

        if any(k in cap_text for k in ["转化", "白名单"]):
            add_tag("conversion_prediction")
        if any(k in cap_text for k in ["首贷"]):
            add_tag("first_loan")
            add_tag("conversion_prediction")

        if any(k in cap_text for k in ["名单", "排序", "优先级"]):
            add_tag("priority_ranking")
            add_tag("ranking")
            add_tag("ranked_list")

        if any(k in cap_text for k in ["需求", "预测需求"]):
            add_tag("demand_forecasting")

        if any(k in cap_text for k in ["绩效", "时效", "效率"]):
            add_tag("performance_analysis")

        if any(k in cap_text for k in ["资源", "排班", "调配", "客流"]):
            add_tag("resource_optimization")
            add_tag("resource_planning")

        if any(k in cap_text for k in ["偏好", "推荐", "匹配"]):
            add_tag("preference_analysis")

        if any(k in cap_text for k in ["价值", "高价值"]):
            add_tag("value_assessment")
            add_tag("lifetime_value")
