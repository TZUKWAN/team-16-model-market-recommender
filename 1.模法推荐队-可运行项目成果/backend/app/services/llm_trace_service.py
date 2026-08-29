"""Non-sensitive audit trail for LLM calls."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.request_context import get_correlation_id, get_request_id


class LLMTraceService:
    """Append-only JSONL trace writer for LLM calls.

    The trace intentionally stores hashes and counts instead of raw prompts,
    responses, Authorization headers, or API keys.
    """

    def __init__(self, trace_dir: Path | None = None, enabled: bool | None = None):
        settings = get_settings()
        self.enabled = settings.LLM_TRACE_ENABLED if enabled is None else enabled
        self.trace_dir = trace_dir or settings.LLM_TRACE_DIR
        self.trace_path = self.trace_dir / "llm_calls.jsonl"

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def endpoint_host(endpoint: str) -> str:
        parsed = urlparse(endpoint)
        return parsed.netloc or ""

    @staticmethod
    def estimate_tokens(*texts: str) -> int:
        total_chars = sum(len(t or "") for t in texts)
        return max(1, total_chars // 2) if total_chars else 0

    @staticmethod
    def new_trace_id() -> str:
        return f"llm_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def start_timer() -> float:
        return time.perf_counter()

    def record(
        self,
        *,
        trace_id: str,
        operation: str,
        provider: str,
        model: str,
        endpoint: str,
        system_prompt: str,
        user_message: str,
        success: bool,
        started_at: float,
        response_text: str = "",
        error_type: str = "",
        status_code: int | None = None,
        attempts: int = 1,
        usage: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        usage = usage or {}
        input_chars = len(system_prompt or "") + len(user_message or "")
        output_chars = len(response_text or "")
        record = {
            "trace_id": trace_id,
            "request_id": get_request_id(),
            "correlation_id": get_correlation_id(),
            "timestamp": self.now_iso(),
            "operation": operation,
            "provider": provider,
            "model": model,
            "endpoint_host": self.endpoint_host(endpoint),
            "success": success,
            "status_code": status_code,
            "error_type": error_type,
            "attempts": attempts,
            "elapsed_ms": elapsed_ms,
            "input_chars": input_chars,
            "output_chars": output_chars,
            "system_prompt_hash": self.text_hash(system_prompt or ""),
            "user_message_hash": self.text_hash(user_message or ""),
            "response_hash": self.text_hash(response_text or "") if response_text else "",
            "estimated_input_tokens": usage.get("prompt_tokens") or self.estimate_tokens(system_prompt, user_message),
            "estimated_output_tokens": usage.get("completion_tokens") or self.estimate_tokens(response_text),
            "total_tokens": usage.get("total_tokens"),
        }
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        with self.trace_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record


_llm_trace_service: LLMTraceService | None = None


def get_llm_trace_service() -> LLMTraceService:
    global _llm_trace_service
    if _llm_trace_service is None:
        _llm_trace_service = LLMTraceService()
    return _llm_trace_service


def reset_llm_trace_service_for_tests() -> None:
    global _llm_trace_service
    _llm_trace_service = None
