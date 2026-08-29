#!/usr/bin/env python3
"""Smoke-test the end-to-end API demo flow.

Default mode runs in-process with FastAPI TestClient. Use --base-url to test a
running backend service over HTTP.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
DEFAULT_REPORT = BASE_DIR / "reports" / "smoke_api_results.json"

sys.path.insert(0, str(BACKEND_DIR))


SCENARIOS = [
    {
        "id": "marketing_first_loan",
        "name": "县域新客首贷营销",
        "query": "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。",
        "expected_intent": "customer_marketing",
        "expected_keyword_groups": [["首贷", "新客"], ["营销", "转化", "conversion"]],
    },
    {
        "id": "pre_loan_risk",
        "name": "农户小额贷款贷前风控",
        "query": "帮我做农户小额贷款的贷前准入风控，最好能识别欺诈风险并给出额度建议。",
        "expected_intent": "credit_risk",
        "expected_keyword_groups": [["农户", "小额", "经营贷款"], ["准入", "反欺诈", "额度", "admission", "fraud"]],
    },
    {
        "id": "post_loan_warning",
        "name": "对公贷款贷后预警",
        "query": "我想提前发现对公贷款可能逾期的客户，并给客户经理一个预警名单。",
        "expected_intent": "credit_risk",
        "expected_keyword_groups": [["违约", "逾期", "预警", "default_prediction", "early_warning"]],
    },
    {
        "id": "branch_operation",
        "name": "网点客流与排班运营",
        "query": "网点客流波动比较大，希望预测高峰时段并辅助排班，减少客户等待。",
        "expected_intent": "operation_management",
        "expected_keyword_groups": [["网点", "运营"], ["客流", "排班", "资源", "resource", "预测"]],
    },
    {
        "id": "churn_retention",
        "name": "高价值客户流失挽留",
        "query": "请帮我识别高价值客户流失风险，输出需要重点挽留的客户名单和跟进优先级。",
        "expected_intent": "customer_marketing",
        "expected_keyword_groups": [["流失", "churn"], ["高价值", "价值", "lifetime"]],
    },
]


class InProcessClient:
    def __init__(self):
        from fastapi.testclient import TestClient
        from app.main import app

        self.client = TestClient(app)

    def get(self, path: str) -> tuple[int, dict[str, Any] | str]:
        response = self.client.get(path)
        return response.status_code, _response_payload(response)

    def post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
        response = self.client.post(path, json=payload)
        return response.status_code, _response_payload(response)


class HttpClient:
    def __init__(self, base_url: str, timeout_seconds: int = 90):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get(self, path: str) -> tuple[int, dict[str, Any] | str]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return response.status, {}
                try:
                    return response.status, json.loads(body)
                except json.JSONDecodeError:
                    return response.status, body
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body
        except Exception as exc:
            return 0, f"{exc.__class__.__name__}: {exc}"


def _response_payload(response: Any) -> dict[str, Any] | str:
    try:
        return response.json()
    except Exception:
        return response.text


def assert_status(status: int, expected: int, step: str, payload: Any) -> None:
    if status != expected:
        raise AssertionError(f"{step} expected HTTP {expected}, got {status}: {str(payload)[:300]}")


def run_scenario(client: InProcessClient | HttpClient, scenario: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    steps: list[dict[str, Any]] = []

    status, health = client.get("/api/v1/health")
    assert_status(status, 200, "health", health)
    steps.append({"step": "health", "status": status})

    status, parse_data = client.post("/api/v1/parse-demand", {"raw_text": scenario["query"]})
    assert_status(status, 200, "parse-demand", parse_data)
    if not isinstance(parse_data, dict):
        raise AssertionError("parse-demand returned non-JSON payload")
    if parse_data.get("intent") != scenario["expected_intent"]:
        raise AssertionError(
            f"scenario {scenario['id']} expected intent {scenario['expected_intent']}, got {parse_data.get('intent')}"
        )
    steps.append({"step": "parse-demand", "status": status, "intent": parse_data.get("intent")})

    status, recommend_data = client.post(
        "/api/v1/recommend-models",
        {"parse_result": parse_data, "top_k": 5},
    )
    assert_status(status, 200, "recommend-models", recommend_data)
    if not isinstance(recommend_data, dict) or len(recommend_data.get("recommendations", [])) < 3:
        raise AssertionError("recommend-models returned fewer than 3 recommendations")
    top_model = recommend_data["recommendations"][0]
    if not top_model.get("recommendation_reason"):
        raise AssertionError("top recommendation is missing recommendation_reason")
    recommendation_text = " ".join(
        f"{item.get('model_name', '')} {item.get('recommendation_reason', '')} {' '.join(item.get('output_fields', []))}"
        for item in recommend_data.get("recommendations", [])
    )
    missing_groups = [
        group for group in scenario["expected_keyword_groups"]
        if not any(keyword in recommendation_text for keyword in group)
    ]
    if missing_groups:
        raise AssertionError(f"recommendations missing expected business keyword groups: {missing_groups}")
    steps.append({
        "step": "recommend-models",
        "status": status,
        "top_model_id": top_model.get("model_id"),
        "top_model_name": top_model.get("model_name"),
    })

    status, composition_data = client.post("/api/v1/recommend-composition", {"parse_result": parse_data})
    assert_status(status, 200, "recommend-composition", composition_data)
    if not isinstance(composition_data, dict) or not composition_data.get("nodes"):
        raise AssertionError("recommend-composition returned no nodes")
    steps.append({"step": "recommend-composition", "status": status, "node_count": len(composition_data["nodes"])})

    model_id = top_model["model_id"]
    status, detail_data = client.get(f"/api/v1/models/{model_id}")
    assert_status(status, 200, "model-detail", detail_data)
    if not isinstance(detail_data, dict) or detail_data.get("model_id") != model_id:
        raise AssertionError("model detail did not match selected model")
    steps.append({"step": "model-detail", "status": status})

    status, report_data = client.post(
        "/api/v1/reports/recommendation",
        {
            "request_id": recommend_data.get("request_id", scenario["id"]),
            "format": "markdown",
            "parse_result": parse_data,
            "recommend_result": recommend_data,
            "composition_result": composition_data,
        },
    )
    assert_status(status, 200, "report", report_data)
    if not isinstance(report_data, dict) or not report_data.get("raw_content"):
        raise AssertionError("report response is missing raw_content")
    steps.append({"step": "report", "status": status, "section_count": len(report_data.get("sections", []))})

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "status": "passed",
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "steps": steps,
    }


def run_smoke(base_url: str = "", limit: int = 0) -> dict[str, Any]:
    client: InProcessClient | HttpClient = HttpClient(base_url) if base_url else InProcessClient()
    selected = SCENARIOS[:limit] if limit else SCENARIOS
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    status, root_payload = client.get("/")
    assert_status(status, 200, "root", root_payload)
    status, metrics_payload = client.get("/api/v1/evaluation/metrics")
    assert_status(status, 200, "evaluation metrics", metrics_payload)

    for scenario in selected:
        try:
            results.append(run_scenario(client, scenario))
        except Exception as exc:
            failures.append({
                "id": scenario["id"],
                "name": scenario["name"],
                "status": "failed",
                "error": str(exc),
            })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "http" if base_url else "in_process",
        "base_url": base_url,
        "scenario_count": len(selected),
        "passed_count": len(results),
        "failed_count": len(failures),
        "passed": len(failures) == 0,
        "results": results,
        "failures": failures,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the model market assistant API.")
    parser.add_argument("--base-url", default="", help="Optional running backend base URL, e.g. http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of scenarios for quick checks.")
    parser.add_argument("--output", default=str(DEFAULT_REPORT), help="JSON report output path.")
    args = parser.parse_args()

    report = run_smoke(base_url=args.base_url, limit=args.limit)
    write_report(Path(args.output), report)
    print(f"Smoke mode: {report['mode']}")
    print(f"Passed: {report['passed_count']} / {report['scenario_count']}")
    print(f"Failed: {report['failed_count']}")
    print(f"Report: {Path(args.output)}")
    if not report["passed"]:
        for failure in report["failures"]:
            print(f"FAIL {failure['id']}: {failure['error']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
