"""Request JSON-complexity helpers."""

from __future__ import annotations

from typing import Any


def json_depth(value: Any) -> int:
    if not isinstance(value, (dict, list)) or not value:
        return 1
    children = value.values() if isinstance(value, dict) else value
    return 1 + max(json_depth(child) for child in children)
