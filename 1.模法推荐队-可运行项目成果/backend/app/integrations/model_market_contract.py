"""Versioned model-market response contracts and evidence hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ModelDetailContract(ContractModel):
    model_id: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    result_schema: dict[str, Any]


class InvokeContract(ContractModel):
    model_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    status: Literal["submitted", "running", "succeeded", "failed"]
    result: dict[str, Any] = Field(default_factory=dict)


class TaskStatusContract(ContractModel):
    task_id: str = Field(min_length=1)
    status: Literal["submitted", "running", "succeeded", "failed"]


class ModelResultContract(ContractModel):
    task_id: str = Field(min_length=1)
    status: Literal["submitted", "running", "succeeded", "failed"]
    result: dict[str, Any]


class ResultSchemaContract(ContractModel):
    model_id: str = Field(min_length=1)
    result_schema: dict[str, Any]


CONTRACT_MODELS = {
    "model_detail": ModelDetailContract,
    "invoke": InvokeContract,
    "task_status": TaskStatusContract,
    "model_result": ModelResultContract,
    "result_schema": ResultSchemaContract,
}


def contract_hash() -> str:
    schemas = {name: model.model_json_schema() for name, model in CONTRACT_MODELS.items()}
    encoded = json.dumps(schemas, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def contract_evidence_status() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[3]
    path = root / "reports" / "contracts" / "model_market_contract_results.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"contract_tested": False, "contract_hash": contract_hash()}
    tested = payload.get("status") == "passed" and payload.get("contract_hash") == contract_hash()
    return {"contract_tested": tested, "contract_hash": contract_hash()}
