#!/usr/bin/env python3
"""Smoke test the configured LLM provider without printing secrets."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.llm_client import LLMClient  # noqa: E402


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
        print("SKIP: LLM is not enabled. Configure LLM_PROVIDER, LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY.")
        return 0

    result = client.chat(
        "你是一个连通性测试助手，只能用一句中文回答。",
        "请回复：LLM_SMOKE_OK",
        temperature=0.0,
    )
    if not result:
        print("FAIL: LLM request returned no content.")
        return 1
    print(f"LLM response preview: {result[:80]}")
    if "LLM_SMOKE_OK" not in result:
        print("WARN: LLM responded, but did not echo the expected marker.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
