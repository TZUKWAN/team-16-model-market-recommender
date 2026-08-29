"""Unified LLM client for OpenAI-compatible chat completion APIs.

The client is intentionally conservative:
- API keys are read from environment/settings only.
- Secrets are never exposed through status or log messages.
- A missing API key disables LLM features instead of pretending success.
"""

from __future__ import annotations
import json
import hashlib
import logging
import os
import threading
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm_trace_service import LLMTraceService, get_llm_trace_service

logger = logging.getLogger(__name__)


DEFAULT_PROVIDER_URLS = {
    "bigmodel": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

DEFAULT_PROVIDER_MODELS = {
    "bigmodel": "glm-4.7-flash",
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
}


class LLMClient:
    """Lightweight LLM client for structured prompting."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "",
        model: str = "",
        provider: str = "",
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        trace_service: LLMTraceService | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        settings = get_settings()
        explicit_provider = bool(provider)
        self.provider = (provider or settings.LLM_PROVIDER or os.getenv("LLM_PROVIDER", "mock")).lower()
        self.api_key = api_key or settings.LLM_API_KEY or os.getenv("LLM_API_KEY", "")
        configured_base_url = base_url or ("" if explicit_provider else settings.LLM_BASE_URL or os.getenv("LLM_BASE_URL", ""))
        configured_model = model or ("" if explicit_provider else settings.LLM_MODEL or os.getenv("LLM_MODEL", ""))
        self.base_url = self._resolve_base_url(configured_base_url)
        self.model = configured_model or DEFAULT_PROVIDER_MODELS.get(self.provider, "")
        self.timeout_seconds = int(timeout_seconds or settings.LLM_TIMEOUT_SECONDS)
        self.connect_timeout_seconds = float(settings.LLM_CONNECT_TIMEOUT_SECONDS)
        self.read_timeout_seconds = float(timeout_seconds or settings.LLM_READ_TIMEOUT_SECONDS)
        self.total_timeout_seconds = float(settings.LLM_TOTAL_TIMEOUT_SECONDS)
        self.max_retries = int(max_retries if max_retries is not None else settings.LLM_MAX_RETRIES)
        self.circuit_failure_threshold = max(1, int(settings.LLM_CIRCUIT_FAILURE_THRESHOLD))
        self.circuit_open_seconds = max(0.01, float(settings.LLM_CIRCUIT_OPEN_SECONDS))
        self.cache_enabled = bool(settings.LLM_CACHE_ENABLED)
        self.cache_ttl_seconds = max(0.0, float(settings.LLM_CACHE_TTL_SECONDS))
        self._available = self.provider != "mock" and bool(self.api_key) and bool(self.base_url) and bool(self.model)
        self.trace_service = trace_service or get_llm_trace_service()
        self.last_trace_id = ""
        self.last_call_status: dict[str, Any] = {"status": "not_called"}
        self._transport = transport
        self._state_lock = threading.RLock()
        self._circuit_state = "closed"
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._half_open_inflight = False
        self._cache: dict[str, tuple[float, str]] = {}

    @property
    def available(self) -> bool:
        return self._available

    @property
    def endpoint(self) -> str:
        return self.base_url

    def status(self) -> dict[str, Any]:
        """Return non-sensitive LLM status for health checks."""
        return {
            "llm_enabled": self.available,
            "llm_provider": self.provider,
            "llm_model": self.model if self.available or self.model else "",
            "llm_base_url_configured": bool(self.base_url),
            "llm_api_key_configured": bool(self.api_key),
            "llm_timeout_seconds": self.timeout_seconds,
            "llm_connect_timeout_seconds": self.connect_timeout_seconds,
            "llm_read_timeout_seconds": self.read_timeout_seconds,
            "llm_total_timeout_seconds": self.total_timeout_seconds,
            "llm_max_retries": self.max_retries,
            "llm_circuit_state": self._current_circuit_state(),
            "llm_cache_enabled": self.cache_enabled,
            "llm_last_call_status": self.last_call_status.get("status", "not_called"),
        }

    def _resolve_base_url(self, configured: str) -> str:
        url = (configured or DEFAULT_PROVIDER_URLS.get(self.provider, "")).strip()
        if not url:
            return ""
        url = url.rstrip("/")
        if url.endswith("/chat/completions"):
            return url
        if url.endswith("/v1"):
            return f"{url}/chat/completions"
        if url.endswith("/paas/v4"):
            return f"{url}/chat/completions"
        return f"{url}/v1/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _request_body(self, system_prompt: str, user_message: str, temperature: float) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": 4096,
        }
        if "qwen" in self.model.lower():
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    def _current_circuit_state(self) -> str:
        with self._state_lock:
            if self._circuit_state == "open" and time.monotonic() - self._opened_at >= self.circuit_open_seconds:
                return "half_open"
            return self._circuit_state

    def _acquire_circuit(self) -> bool:
        with self._state_lock:
            if self._circuit_state == "open":
                if time.monotonic() - self._opened_at < self.circuit_open_seconds:
                    return False
                if self._half_open_inflight:
                    return False
                self._circuit_state = "half_open"
                self._half_open_inflight = True
            return True

    def _record_circuit_success(self) -> None:
        with self._state_lock:
            self._circuit_state = "closed"
            self._consecutive_failures = 0
            self._half_open_inflight = False

    def _record_circuit_failure(self) -> None:
        with self._state_lock:
            self._consecutive_failures += 1
            if self._circuit_state == "half_open" or self._consecutive_failures >= self.circuit_failure_threshold:
                self._circuit_state = "open"
                self._opened_at = time.monotonic()
            self._half_open_inflight = False

    def _cache_key(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float,
        prompt_version: str,
        cache_context: dict[str, Any],
    ) -> str:
        payload = {
            "provider": self.provider,
            "model": self.model,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "temperature": temperature,
            "prompt_version": prompt_version,
            "cache_context": cache_context,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _perform_request(self, body: dict[str, Any], remaining_seconds: float) -> tuple[int, dict[str, Any]]:
        timeout = httpx.Timeout(
            connect=min(self.connect_timeout_seconds, remaining_seconds),
            read=min(self.read_timeout_seconds, remaining_seconds),
            write=min(self.connect_timeout_seconds, remaining_seconds),
            pool=min(self.connect_timeout_seconds, remaining_seconds),
        )
        with httpx.Client(timeout=timeout, transport=self._transport) as client:
            response = client.post(self.endpoint, headers=self._headers(), json=body)
        status_code = response.status_code
        if status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {status_code}", request=response.request, response=response
            )
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("invalid_response_shape")
        return status_code, result

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        *,
        prompt_version: str = "v1",
        cache_context: dict[str, Any] | None = None,
    ) -> str | None:
        """Send a chat request to the LLM. Returns None on failure."""
        if not self.available:
            self.last_call_status = {"status": "unavailable", "reason": "llm_not_configured"}
            return None
        body = self._request_body(system_prompt, user_message, temperature)
        cache_key = self._cache_key(
            system_prompt, user_message, temperature, prompt_version, cache_context or {}
        )
        if self.cache_enabled:
            with self._state_lock:
                cached = self._cache.get(cache_key)
                if cached and cached[0] >= time.monotonic():
                    self.last_call_status = {"status": "cache_hit", "attempts": 0}
                    return cached[1]
                if cached:
                    self._cache.pop(cache_key, None)
        if not self._acquire_circuit():
            self.last_call_status = {"status": "fallback", "reason": "circuit_open", "attempts": 0}
            return None
        last_error = ""
        status_code: int | None = None
        trace_id = self.trace_service.new_trace_id()
        self.last_trace_id = trace_id
        started_at = self.trace_service.start_timer()
        deadline = time.monotonic() + self.total_timeout_seconds
        attempts = 0
        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("total_timeout")
                status_code, result = self._perform_request(body, remaining)
                message = result["choices"][0]["message"]
                content = message.get("content")
                if content is None:
                    content = message.get("reasoning_content") or ""
                response_text = str(content).strip()
                if not response_text:
                    raise ValueError("empty_response")
                self.trace_service.record(
                    trace_id=trace_id,
                    operation="chat",
                    provider=self.provider,
                    model=self.model,
                    endpoint=self.endpoint,
                    system_prompt=system_prompt,
                    user_message=user_message,
                    success=True,
                    started_at=started_at,
                    response_text=response_text,
                    status_code=status_code,
                    attempts=attempts,
                    usage=result.get("usage") if isinstance(result, dict) else None,
                )
                self._record_circuit_success()
                if self.cache_enabled and self.cache_ttl_seconds > 0:
                    with self._state_lock:
                        self._cache[cache_key] = (time.monotonic() + self.cache_ttl_seconds, response_text)
                self.last_call_status = {
                    "status": "success", "attempts": attempts, "status_code": status_code,
                    "trace_id": trace_id,
                }
                return response_text
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                last_error = f"HTTP {status_code}"
                if status_code < 500 and status_code not in {408, 429}:
                    break
            except httpx.ConnectError as exc:
                last_error = exc.__class__.__name__
            except (httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                # The provider may have processed a timed-out request; do not
                # retry and risk duplicate billing.
                last_error = exc.__class__.__name__
                break
            except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = str(exc)[:80] or exc.__class__.__name__
                break
            except Exception as exc:
                last_error = exc.__class__.__name__
                break
            if attempt < self.max_retries:
                delay = min(2 ** attempt, 4)
                if time.monotonic() + delay >= deadline:
                    last_error = "total_timeout"
                    break
                time.sleep(delay)
        logger.warning(
            "LLM call failed for provider=%s model=%s endpoint_configured=%s error=%s; falling back to rules",
            self.provider,
            self.model,
            bool(self.endpoint),
            last_error,
        )
        self.trace_service.record(
            trace_id=trace_id,
            operation="chat",
            provider=self.provider,
            model=self.model,
            endpoint=self.endpoint,
            system_prompt=system_prompt,
            user_message=user_message,
            success=False,
            started_at=started_at,
            error_type=last_error,
            status_code=status_code,
            attempts=attempts,
        )
        self._record_circuit_failure()
        self.last_call_status = {
            "status": "fallback", "reason": last_error or "unknown_error",
            "attempts": attempts, "status_code": status_code, "trace_id": trace_id,
        }
        return None

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        *,
        prompt_version: str = "v1",
        cache_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Send a chat request expecting JSON response."""
        result = self.chat(
            system_prompt,
            user_message,
            temperature,
            prompt_version=prompt_version,
            cache_context=cache_context,
        )
        if not result:
            return None
        try:
            # Try to extract JSON from markdown code blocks
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]
            elif "```" in result:
                result = result.split("```")[1].split("```")[0]
            # Handle truncated JSON: complete missing closing braces
            if result.strip().startswith("{") and not result.strip().endswith("}"):
                result = result.rstrip() + "\n}"
            return json.loads(result)
        except json.JSONDecodeError:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                logger.warning(f"LLM did not return valid JSON: {result[:200]}")
                return None


# Global singleton
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def reset_llm_client_for_tests() -> None:
    """Reset singleton in tests after environment/config changes."""
    global _llm_client
    _llm_client = None
