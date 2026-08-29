#!/usr/bin/env python3
"""Smoke test LLM-backed demand parsing on 50 banking requirements.

Secrets are read only from environment variables and are never printed.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.demand_parser import DemandParser  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402


SAMPLES = [
    "帮我做农户小额贷款的贷前准入风控，识别欺诈风险并给出额度建议。",
    "我想筛一批县域新客，做首贷营销，输出转化概率高的名单。",
    "提前发现对公贷款可能逾期的客户，并给客户经理预警名单。",
    "网点客流预测和智能排班，看看高峰期在哪里。",
    "反洗钱可疑交易监测，输出需要复核的账户清单。",
    "小微企业贷款全流程风控，需要准入评分和贷后预警。",
    "识别沉睡客户并给出唤醒营销优先级。",
    "预测客户流失风险，给出挽留建议。",
    "对公客户交叉销售，推荐适合的结算和贷款产品。",
    "柜面业务异常识别，发现操作风险。",
] * 5


def main() -> int:
    client = LLMClient()
    status = client.status()
    safe_status = {
        "llm_enabled": status["llm_enabled"],
        "llm_provider": status["llm_provider"],
        "llm_model": status["llm_model"],
        "llm_base_url_configured": status["llm_base_url_configured"],
        "llm_api_key_configured": status["llm_api_key_configured"],
    }
    print(f"LLM status: {safe_status}")
    if not client.available:
        print("SKIP: configure LLM_PROVIDER=bigmodel, LLM_MODEL=glm-4.7-flash, and LLM_API_KEY to run live smoke.")
        return 0

    parser = DemandParser()
    counts: Counter[str] = Counter()
    failures: list[str] = []
    for index, sample in enumerate(SAMPLES, start=1):
        result = parser.parse(sample)
        counts[result.parse_source] += 1
        if result.parse_source not in {"llm", "hybrid_fallback"}:
            failures.append(f"{index}: unexpected source {result.parse_source}")
        if not result.intent or not result.tags:
            failures.append(f"{index}: missing intent/tags")
        print(f"{index:02d} source={result.parse_source} intent={result.intent} tags={len(result.tags)}")

    print(f"Source counts: {dict(counts)}")
    if failures:
        print("FAILURES:")
        for item in failures[:10]:
            print(f"- {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
