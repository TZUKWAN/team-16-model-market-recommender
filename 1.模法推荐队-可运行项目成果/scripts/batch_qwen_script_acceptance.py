#!/usr/bin/env python3
"""
F3.2: Three-domain real Qwen batch script generation acceptance.

Generates scenario scripts for 9 scenarios (3 per domain) using real Qwen,
records provider/model/trace/status/length/compliance for each, and writes
a structured evidence file.

Usage:
    python scripts/batch_qwen_script_acceptance.py

Output: reports/scenario_scripts/qwen_live_acceptance.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

from app.services.script_generator import ScriptGenerator

SCENARIOS = [
    # customer_marketing
    {"scenario_id": "SCN_011", "domain": "customer_marketing", "name": "县域新客首贷营销", "script_type": "marketing", "raw_text": "我想筛选县域新客做首贷营销，需要转化概率高的客户名单"},
    {"scenario_id": "SCN_012", "domain": "customer_marketing", "name": "高价值客户流失挽留", "script_type": "marketing", "raw_text": "需要识别可能流失的高价值客户并制定挽留策略"},
    {"scenario_id": "SCN_013", "domain": "customer_marketing", "name": "信用卡交叉销售", "script_type": "comprehensive", "raw_text": "想给存量客户推荐合适的信用卡产品"},
    # credit_risk
    {"scenario_id": "SCN_001", "domain": "credit_risk", "name": "农户小额贷款贷前准入", "script_type": "risk_notice", "raw_text": "农户小额贷款贷前风险评估，需要准入评分和欺诈检测"},
    {"scenario_id": "SCN_002", "domain": "credit_risk", "name": "个人消费贷款贷前反欺诈", "script_type": "risk_notice", "raw_text": "个人消费贷款申请需要反欺诈筛查"},
    {"scenario_id": "SCN_003", "domain": "credit_risk", "name": "小微企业贷款额度测算", "script_type": "comprehensive", "raw_text": "小微企业贷款需要额度测算和信用评级"},
    # operation_management
    {"scenario_id": "SCN_021", "domain": "operation_management", "name": "网点客流预测与排班", "script_type": "outreach", "raw_text": "需要预测网点客流量并优化排班"},
    {"scenario_id": "SCN_022", "domain": "operation_management", "name": "柜台业务量预测", "script_type": "outreach", "raw_text": "需要预测柜台业务量并合理调配人员"},
    {"scenario_id": "SCN_023", "domain": "operation_management", "name": "渠道交易异常监测", "script_type": "risk_notice", "raw_text": "需要监测渠道交易异常并预警"},
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports" / "scenario_scripts"


def run_acceptance() -> dict:
    gen = ScriptGenerator()
    llm_available = gen.llm.available
    provider = gen.llm.provider if llm_available else "unavailable"
    model = gen.llm.model if llm_available else "unavailable"

    results = []
    success_count = 0
    for sc in SCENARIOS:
        resp = gen.generate(
            scenario_id=sc["scenario_id"],
            parse_result={"raw_text": sc["raw_text"], "business_scenario": sc["name"]},
            script_type=sc["script_type"],
        )
        script = resp.script
        record = {
            "scenario_id": sc["scenario_id"],
            "domain": sc["domain"],
            "scenario_name": sc["name"],
            "script_type": sc["script_type"],
            "llm_used": script.llm_used,
            "provider": script.llm_provider or provider,
            "model": script.llm_model or model,
            "trace_id": script.llm_trace_id,
            "status": script.status,
            "repair_attempted": script.repair_attempted,
            "fallback_reason": script.fallback_reason,
            "content_length": len(script.content),
            "has_compliance_note": "合规" in script.content or "人工复核" in script.content,
            "has_human_review_note": "人工复核" in script.content,
            "validation_valid": script.validation.get("valid", False),
            "validation_violations": script.validation.get("violations", []),
            "has_illegal_model_id": any("未授权模型ID" in v for v in script.validation.get("violations", [])),
        }
        results.append(record)
        if script.llm_used and script.status in ("ok", "repaired"):
            success_count += 1
        print(f"  {sc['domain']}/{sc['scenario_id']}: llm_used={script.llm_used}, status={script.status}, len={len(script.content)}, trace={script.llm_trace_id[:20] if script.llm_trace_id else 'N/A'}")

    total = len(SCENARIOS)
    summary = {
        "generated_at": datetime.now().isoformat(),
        "provider": provider,
        "model": model,
        "llm_available": llm_available,
        "total_scenarios": total,
        "llm_success_count": success_count,
        "success_rate": round(success_count / total, 4) if total else 0,
        "all_have_compliance": all(r["has_compliance_note"] for r in results),
        "all_have_human_review": all(r["has_human_review_note"] for r in results),
        "any_illegal_model_id": any(r["has_illegal_model_id"] for r in results),
        "results": results,
        "acceptance_criteria": {
            "success_rate_target": ">=95% (9/9 for this sample)",
            "illegal_model_id_target": "0",
            "compliance_note_target": "all true",
            "human_review_note_target": "all true",
        },
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "qwen_live_acceptance.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nEvidence saved to: {output_path}")
    print(f"Success rate: {success_count}/{total} ({summary['success_rate']*100:.1f}%)")
    print(f"Illegal model IDs: {summary['any_illegal_model_id']}")
    print(f"All compliance notes: {summary['all_have_compliance']}")
    return summary


if __name__ == "__main__":
    run_acceptance()
