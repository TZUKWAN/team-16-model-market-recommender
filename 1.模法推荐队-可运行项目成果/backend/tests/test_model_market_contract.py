from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.integrations.model_market_contract import contract_evidence_status, contract_hash


ROOT = Path(__file__).resolve().parents[2]


def _acceptance_module():
    spec = spec_from_file_location(
        "run_model_market_contract_acceptance",
        ROOT / "scripts" / "run_model_market_contract_acceptance.py",
    )
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_contract_sandbox_covers_required_behaviors():
    payload = await _acceptance_module().run_acceptance()
    assert payload["status"] == "passed"
    assert payload["contract_hash"] == contract_hash()
    assert payload["real_bank_connected"] is False
    assert set(payload["cases"]) == {
        "model_detail", "sync_invoke", "async_task", "result_schema",
        "upstream_failure", "permission_denied", "schema_change", "timeout",
    }
    assert set(payload["cases"].values()) == {"passed"}


def test_health_reports_contract_evidence_separately_from_real_connection(client):
    evidence = contract_evidence_status()
    response = client.get("/api/v1/health")
    assert evidence["contract_tested"] is True
    assert response.status_code == 200
    assert response.json()["model_market_contract_tested"] is True
    assert response.json()["model_market_real_connected"] is False
