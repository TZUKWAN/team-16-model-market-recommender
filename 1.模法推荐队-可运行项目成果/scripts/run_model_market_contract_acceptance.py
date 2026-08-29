"""Run the HTTP adapter against the local contract sandbox and write evidence."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.integrations.base import ModelMarketContractError, ModelMarketUpstreamError  # noqa: E402
from app.integrations.contract_sandbox import app  # noqa: E402
from app.integrations.http_model_market_client import HttpModelMarketClient  # noqa: E402
from app.integrations.model_market_contract import contract_hash  # noqa: E402


def sandbox_factory(**kwargs):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://sandbox",
        timeout=kwargs.get("timeout", 30),
    )


async def run_acceptance() -> dict:
    client = HttpModelMarketClient(
        base_url="http://sandbox",
        api_key="contract-test-key",
        timeout_seconds=1,
        client_factory=sandbox_factory,
    )
    cases: dict[str, str] = {}
    detail = await client.get_model_detail("OFFICIAL_001")
    cases["model_detail"] = "passed" if detail["model_id"] == "OFFICIAL_001" else "failed"
    sync_result = await client.invoke_model("OFFICIAL_001", {"input_data": {}, "async_mode": False})
    cases["sync_invoke"] = "passed" if sync_result["status"] == "succeeded" else "failed"
    async_result = await client.invoke_model("OFFICIAL_001", {"input_data": {}, "async_mode": True})
    status = await client.get_task_status(async_result["task_id"])
    result = await client.get_model_result(async_result["task_id"])
    cases["async_task"] = "passed" if status["status"] == result["status"] == "succeeded" else "failed"
    schema = await client.get_result_schema("OFFICIAL_001")
    cases["result_schema"] = "passed" if schema["result_schema"]["type"] == "object" else "failed"

    try:
        await client.invoke_model("OFFICIAL_001", {"input_data": {"_contract_case": "failure"}})
        cases["upstream_failure"] = "failed"
    except ModelMarketUpstreamError:
        cases["upstream_failure"] = "passed"
    denied = HttpModelMarketClient(
        base_url="http://sandbox", api_key="wrong-key", client_factory=sandbox_factory
    )
    try:
        await denied.get_model_detail("OFFICIAL_001")
        cases["permission_denied"] = "failed"
    except ModelMarketUpstreamError:
        cases["permission_denied"] = "passed"
    try:
        await client.invoke_model(
            "OFFICIAL_001", {"input_data": {"_contract_case": "schema_change"}}
        )
        cases["schema_change"] = "failed"
    except ModelMarketContractError:
        cases["schema_change"] = "passed"

    def timeout_handler(request):
        raise httpx.ReadTimeout("sandbox timeout", request=request)

    timeout_client = HttpModelMarketClient(
        base_url="http://sandbox",
        api_key="contract-test-key",
        client_factory=lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(timeout_handler), timeout=kwargs.get("timeout", 1)
        ),
    )
    try:
        await timeout_client.get_model_detail("OFFICIAL_001")
        cases["timeout"] = "failed"
    except ModelMarketUpstreamError:
        cases["timeout"] = "passed"

    return {
        "status": "passed" if all(value == "passed" for value in cases.values()) else "failed",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "contract_hash": contract_hash(),
        "real_bank_connected": False,
        "sandbox": True,
        "cases": cases,
    }


def main() -> int:
    payload = asyncio.run(run_acceptance())
    report = ROOT / "reports" / "contracts" / "model_market_contract_results.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    openapi = ROOT / "docs" / "api" / "model_market_contract.openapi.json"
    openapi.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
