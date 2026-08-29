#!/usr/bin/env python3
"""Scan project text files for likely committed API secrets.

This is a best-effort guardrail, not a replacement for provider-side key
rotation and secret scanning. It intentionally skips generated dependency
folders and binary/build artifacts.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
}
TEXT_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".jsonl",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
    ".txt",
    ".env",
    ".example",
}

LIKELY_SECRET_PATTERNS = [
    re.compile(r"\b[A-Fa-f0-9]{32}\.[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
]


def should_scan(path: Path) -> bool:
    rel_parts = set(path.relative_to(BASE_DIR).parts)
    if rel_parts & SKIP_DIRS:
        return False
    if path.name == ".env":
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name.endswith(".example")


def scan_git_history() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "log", "--all", "-p", "--no-ext-diff", "--format=commit:%H"],
            cwd=BASE_DIR,
            capture_output=True,
            check=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return [f"git history scan could not complete: {type(exc).__name__}"]
    history = result.stdout.decode("utf-8", errors="ignore")
    findings: list[str] = []
    for pattern in LIKELY_SECRET_PATTERNS:
        matches = list(pattern.finditer(history))
        if matches:
            findings.append(f"git history: {len(matches)} likely secret pattern(s)")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git-history", action="store_true", help="Also scan committed patch history.")
    args = parser.parse_args(argv)
    findings: list[str] = []
    env_secret_values = [
        value
        for key, value in os.environ.items()
        if key.endswith("API_KEY") and value and len(value) >= 12
    ]

    for path in BASE_DIR.rglob("*"):
        if not path.is_file() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = path.relative_to(BASE_DIR)
        for pattern in LIKELY_SECRET_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(f"{rel}: likely secret pattern at char {match.start()}")
        for secret in env_secret_values:
            if secret in text:
                findings.append(f"{rel}: contains value of an API_KEY environment variable")

    if args.git_history:
        findings.extend(scan_git_history())

    if findings:
        print("Potential secret leaks found:")
        for item in findings:
            print(f"  - {item}")
        return 1
    scope = "project files and git history" if args.git_history else "project files"
    print(f"No likely API secret leaks found in scanned {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
