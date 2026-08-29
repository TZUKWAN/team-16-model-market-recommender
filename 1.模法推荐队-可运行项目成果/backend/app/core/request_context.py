"""Request correlation context and compact in-process HTTP metrics."""

from __future__ import annotations

from collections import defaultdict
from contextvars import ContextVar
import threading
from typing import Any


request_id_var: ContextVar[str] = ContextVar("request_id", default="")
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_request_id() -> str:
    return request_id_var.get()


def get_correlation_id() -> str:
    return correlation_id_var.get()


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._errors = 0
        self._by_status: dict[str, int] = defaultdict(int)

    def record(self, status_code: int) -> None:
        with self._lock:
            self._total += 1
            self._errors += int(status_code >= 500)
            self._by_status[str(status_code)] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_requests": self._total,
                "server_error_count": self._errors,
                "status_counts": dict(self._by_status),
            }


request_metrics = RequestMetrics()
