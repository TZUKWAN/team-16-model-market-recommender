"""Reproducible HTTP load baseline for offline and limited live-LLM paths."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import time
from typing import Any, Callable

import httpx


ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 2)


def run_case(
    client: httpx.Client,
    name: str,
    method: str,
    path: str,
    payload_factory: Callable[[int], dict[str, Any] | None],
    *,
    samples: int,
    concurrency: int,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    def invoke(index: int) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            response = client.request(
                method,
                path,
                json=payload_factory(index),
                headers=headers,
            )
            return {
                "latency_ms": (time.perf_counter() - started) * 1000,
                "status_code": response.status_code,
                "error": "" if response.status_code < 400 else f"HTTP_{response.status_code}",
            }
        except Exception as exc:
            return {
                "latency_ms": (time.perf_counter() - started) * 1000,
                "status_code": 0,
                "error": exc.__class__.__name__,
            }

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        rows = list(executor.map(invoke, range(samples)))
    latencies = [float(row["latency_ms"]) for row in rows]
    errors: dict[str, int] = {}
    status_codes: dict[str, int] = {}
    for row in rows:
        status = str(row["status_code"])
        status_codes[status] = status_codes.get(status, 0) + 1
        if row["error"]:
            errors[row["error"]] = errors.get(row["error"], 0) + 1
    success_count = sum(1 for row in rows if 200 <= row["status_code"] < 400)
    return {
        "name": name,
        "method": method,
        "path": path,
        "samples": samples,
        "concurrency": concurrency,
        "success_count": success_count,
        "success_rate_pct": round(success_count / samples * 100, 2),
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "max_ms": round(max(latencies), 2),
        "status_codes": status_codes,
        "errors": errors,
    }


def setup_survey(client: httpx.Client) -> str:
    response = client.post(
        "/api/v1/surveys/campaigns",
        headers={"X-User-Id": "admin"},
        json={
            "name": "performance acceptance only",
            "invite_count": 1,
            "samples_per_respondent": 2,
            "minimum_respondents": 1,
            "required_roles": ["business"],
            "required_scenarios": ["credit_risk"],
            "evidence_mode": "acceptance_test",
        },
    )
    response.raise_for_status()
    return str(response.json()["campaign"]["campaign_id"])


def offline_cases(
    client: httpx.Client,
    samples: int,
    concurrency: int,
    only: set[str] | None = None,
) -> list[dict[str, Any]]:
    parse_payload = {
        "raw_text": "筛选县域新客开展首贷营销，输出转化概率和客户名单"
    }
    parsed = client.post("/api/v1/parse-demand", json=parse_payload).json()
    recommend_payload = {"parse_result": parsed, "top_k": 5}
    recommended = client.post("/api/v1/recommend-models", json=recommend_payload).json()
    report_payload = {
        "request_id": recommended.get("request_id", "perf-request"),
        "format": "markdown",
        "parse_result": parsed,
        "recommend_result": recommended,
    }
    compare_payload = {
        "model_ids": ["OFFICIAL_001", "OFFICIAL_002"],
        "parse_result": parsed,
    }
    graph_payload = {
        "parse_result": parsed,
        "model_id": str(recommended.get("recommendations", [{}])[0].get("model_id", "OFFICIAL_001")),
        "max_edges": 80,
    }
    campaign_id = setup_survey(client)
    definitions = [
        ("health", "GET", "/api/v1/health", lambda _: None, max(100, samples), 20),
        ("parse_rule", "POST", "/api/v1/parse-demand", lambda _: parse_payload, samples, concurrency),
        ("recommend_offline", "POST", "/api/v1/recommend-models", lambda _: recommend_payload, samples, concurrency),
        ("compare", "POST", "/api/v1/compare-models", lambda _: compare_payload, samples, concurrency),
        ("graph_match", "POST", "/api/v1/graph/match-path", lambda _: graph_payload, samples, concurrency),
        ("survey_definition", "GET", f"/api/v1/surveys/campaigns/{campaign_id}", lambda _: None, samples, concurrency),
        ("report_markdown", "POST", "/api/v1/reports/recommendation", lambda _: report_payload, max(10, samples // 2), min(5, concurrency)),
    ]
    return [
        run_case(client, name, method, path, factory, samples=count, concurrency=workers)
        for name, method, path, factory, count, workers in definitions
        if not only or name in only
    ]


def llm_cases(client: httpx.Client) -> list[dict[str, Any]]:
    return [
        run_case(
            client,
            "parse_qwen_live",
            "POST",
            "/api/v1/parse-demand",
            lambda index: {
                "raw_text": f"性能验收编号{index + 1}：识别农户小额贷款贷前欺诈风险并输出风险评分"
            },
            samples=5,
            concurrency=1,
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--mode", choices=("offline", "llm"), required=True)
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "performance" / "api_load.json")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--only", default="", help="Comma-separated offline case names")
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        health = client.get("/api/v1/health")
        health.raise_for_status()
        health_payload = health.json()
        only = {item.strip() for item in args.only.split(",") if item.strip()}
        results = offline_cases(client, args.samples, args.concurrency, only) if args.mode == "offline" else llm_cases(client)
    run = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": args.mode,
        "base_url": args.base_url,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "llm_provider": health_payload.get("llm_provider"),
            "llm_model": health_payload.get("llm_model"),
            "llm_enabled": health_payload.get("llm_enabled"),
            "runtime_storage_ready": health_payload.get("runtime_storage_ready"),
        },
        "results": results,
    }
    payload: dict[str, Any] = {"schema_version": 1, "runs": []}
    if args.append and args.output.exists():
        payload = json.loads(args.output.read_text(encoding="utf-8"))
    payload.setdefault("runs", []).append(run)
    latest_by_mode = {
        mode: next(item for item in reversed(payload["runs"]) if item["mode"] == mode)
        for mode in {item["mode"] for item in payload["runs"]}
    }
    latest_results = [result for item in latest_by_mode.values() for result in item["results"]]
    payload["acceptance"] = {
        "no_5xx": all(
            not any(code.startswith("5") and count for code, count in result["status_codes"].items())
            for result in latest_results
        ),
        "latest_runs_all_requests_successful": all(
            result["success_rate_pct"] == 100 for result in latest_results
        ),
        "health_p95_under_200ms": all(
            result["p95_ms"] < 200
            for result in latest_results if result["name"] == "health"
        ),
        "offline_recommend_p95_under_2s": all(
            result["p95_ms"] < 2000
            for result in latest_results if result["name"] == "recommend_offline"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0 if all(result["success_rate_pct"] == 100 for result in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
