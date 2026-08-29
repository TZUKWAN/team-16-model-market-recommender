"""Generate deterministic DOCX/PDF formatting acceptance fixtures.

The generated reports validate export layout only. They are not external business,
model-performance, or real bank model-market evidence.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.report_exporter import get_report_exporter  # noqa: E402
from app.services.report_service import ReportGenerationService  # noqa: E402


class _OfflineLLM:
    available = False


CASES = {
    "marketing": {
        "intent": "customer_marketing",
        "domain": "客户营销",
        "scenario": "县域新客首贷营销",
        "demand": "面向县域新客开展首贷营销，输出可人工复核的优先级名单和转化概率。",
        "prefix": "MKT",
        "models": [
            "县域新客首贷转化预测模型",
            "首贷客户准入与营销响应联合评估模型",
            "县域客户精细化分层及触达优先级排序模型",
            "普惠金融潜在客户识别模型",
            "新客贷款意向识别模型",
        ],
        "missing": ["客户基础画像", "近十二个月交易流水", "营销授权状态"],
    },
    "risk": {
        "intent": "credit_risk",
        "domain": "信贷风控",
        "scenario": "农户小额贷款贷前准入",
        "demand": "对农户小额贷款申请进行贷前风险识别，输出风险分层和人工复核理由。",
        "prefix": "RISK",
        "models": [
            "农户小额贷款贷前综合风险评估模型",
            "涉农客户多源信息准入评分模型",
            "普惠贷款欺诈风险识别模型",
            "征信与交易行为联合违约预测模型",
            "小额信贷申请反欺诈规则增强模型",
        ],
        "missing": ["征信摘要", "贷款申请信息", "反欺诈设备特征"],
    },
    "ops": {
        "intent": "operation_management",
        "domain": "运营管理",
        "scenario": "网点客流预测与弹性排班",
        "demand": "预测网点分时客流并生成可调整的排班建议，保留人工确认和异常回退。",
        "prefix": "OPS",
        "models": [
            "营业网点分时客流预测与弹性排班联合优化模型",
            "节假日及营销活动客流波动预测模型",
            "柜面业务办理时长预测模型",
            "网点服务资源配置优化模型",
            "高峰时段排队风险预警模型",
        ],
        "missing": ["历史叫号流水", "员工技能与班次", "节假日及营销活动日历"],
    },
}


def _recommendations(case: dict[str, object]) -> list[dict[str, object]]:
    prefix = str(case["prefix"])
    names = list(case["models"])
    missing = list(case["missing"])
    return [
        {
            "rank": index,
            "model_name": name,
            "model_id": f"{prefix}_{index:03d}",
            "total_score": round(94.0 - index * 4.25, 2),
            "recommendation_reason": (
                f"与{case['scenario']}的目标、输入数据和输出形式匹配；"
                "分数仅用于本次格式验收夹具，不代表生产效果。"
            ),
            "missing_data": missing[: max(1, 4 - index)],
            "score_breakdown": {
                "scenario_match": 92 - index,
                "customer_match": 88 - index,
                "data_match": 72 - index * 2,
                "output_match": 90 - index,
                "performance": 0,
                "landing_experience": 0,
                "compliance": 85,
            },
            "evidence_cards": [
                {
                    "evidence_type": "formatting_fixture",
                    "evidence_text": "仅验证报告分页、表格和中文排版，不作为业务或模型效果证据。",
                    "confidence": 1.0,
                }
            ],
        }
        for index, name in enumerate(names, start=1)
    ]


def _build_report(case: dict[str, object]):
    recommendations = _recommendations(case)
    parse_result = {
        "raw_text": case["demand"],
        "normalized_query": case["demand"],
        "intent": case["intent"],
        "domain": case["domain"],
        "business_scenario": case["scenario"],
        "tags": [case["intent"], "human_review", "formatting_acceptance"],
        "tag_confidence": {case["intent"]: 0.95, "human_review": 1.0},
        "business_to_model_translation": "将业务目标转换为候选模型检索、约束过滤、排序和人工复核流程。",
        "user_confirmable_summary": case["demand"],
        "expected_outputs": ["优先级列表", "解释理由", "人工复核提示"],
        "customer_segment": ["授权范围内业务对象"],
        "data_conditions": case["missing"],
    }
    composition = {
        "composition_name": f"{case['scenario']}组合流程",
        "total_score": 82.5,
        "scenario": case["scenario"],
        "nodes": [
            {
                "step_order": index,
                "model_name": recommendation["model_name"],
                "capability": capability,
                "input_fields": ["授权数据", "质量校验结果"],
                "output_fields": ["阶段结果", "审计标识"],
            }
            for index, (recommendation, capability) in enumerate(
                zip(recommendations[:3], ["数据校验", "候选评分", "排序与解释"]), start=1
            )
        ],
        "business_explanation": "流程输出必须经过业务人员复核；数据不足时进入阻塞或降级分支。",
        "usage_guide": [
            {
                "step": "步骤一：准备与授权",
                "description": "确认数据用途、机构权限和最小必要字段。",
                "estimated_time": "由实施环境决定",
                "data_preparation": "只使用脱敏验收数据。",
            },
            {
                "step": "步骤二：小范围验证",
                "description": "先验证输入输出契约、解释和人工复核流程。",
                "estimated_time": "由实施环境决定",
                "data_preparation": "记录数据版本与审计标识。",
            },
        ],
        "execution_result": {
            "desensitized_notice": "当前内容为格式与流程验收夹具，不包含真实客户数据。"
        },
    }
    return ReportGenerationService(llm_client=_OfflineLLM()).generate(
        request_id=f"export-acceptance-{case['prefix'].lower()}",
        parse_result=parse_result,
        recommend_result={
            "recommendations": recommendations,
            "summary": "Top5排序分数为格式验收夹具，不能解释为生产模型效果。",
        },
        composition_result=composition,
        include_details=True,
    )


def main() -> None:
    output = ROOT / "reports" / "export_acceptance"
    output.mkdir(parents=True, exist_ok=True)
    exporter = get_report_exporter()
    results = []
    for name, case in CASES.items():
        report = _build_report(case)
        for fmt, content in (("docx", exporter.to_docx(report)), ("pdf", exporter.to_pdf(report))):
            path = output / f"{name}_report.{fmt}"
            path.write_bytes(content)
            results.append(
                {
                    "path": name,
                    "format": fmt,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "file": path.relative_to(ROOT).as_posix(),
                    "source": "deterministic_formatting_acceptance_fixture",
                    "external_business_evidence": False,
                }
            )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "purpose": "DOCX/PDF formatting and rendering acceptance only",
        "external_business_evidence": False,
        "results": results,
    }
    (output / "verification.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
