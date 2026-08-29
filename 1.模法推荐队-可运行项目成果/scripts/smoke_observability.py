"""Verify one correlation ID links parse, recommend and report HTTP logs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8010"
CORRELATION_ID = "acceptance-workflow-observability-001"


def main() -> int:
    headers = {"X-Correlation-ID": CORRELATION_ID, "X-User-Id": "business_user"}
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=60) as client:
        parsed_response = client.post(
            "/api/v1/parse-demand",
            json={"raw_text": "县域新客首贷营销，输出转化概率名单"},
        )
        parsed_response.raise_for_status()
        parsed = parsed_response.json()
        recommend_response = client.post(
            "/api/v1/recommend-models",
            json={"parse_result": parsed, "top_k": 5},
        )
        recommend_response.raise_for_status()
        recommended = recommend_response.json()
        report_response = client.post(
            "/api/v1/reports/recommendation",
            json={
                "request_id": recommended["request_id"],
                "parse_result": parsed,
                "recommend_result": recommended,
            },
        )
        report_response.raise_for_status()
        response_ids = [
            response.headers["X-Request-ID"]
            for response in (parsed_response, recommend_response, report_response)
        ]

    time.sleep(0.2)
    log_path = ROOT / ".codex" / "logs" / "backend.out.log"
    records = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("correlation_id") == CORRELATION_ID and record.get("message", "").startswith("http_request"):
            records.append(record)
    paths = {record["message"].split(" path=", 1)[1].split(" ", 1)[0] for record in records}
    expected = {
        "/api/v1/parse-demand",
        "/api/v1/recommend-models",
        "/api/v1/reports/recommendation",
    }
    payload = {
        "status": "passed" if expected <= paths else "failed",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "correlation_id": CORRELATION_ID,
        "response_request_ids": response_ids,
        "logged_paths": sorted(paths),
        "raw_request_content_recorded": False,
    }
    output = ROOT / "reports" / "observability" / "correlation_smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
