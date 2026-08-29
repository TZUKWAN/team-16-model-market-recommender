"""Local model-market contract sandbox; never represents a bank connection."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse


app = FastAPI(title="Model Market Contract Sandbox", version="1.0.0")
_tasks: dict[str, dict[str, Any]] = {}


def _authorize(authorization: str | None) -> None:
    if authorization != "Bearer contract-test-key":
        raise HTTPException(status_code=403, detail="sandbox permission denied")


@app.get("/models/{model_id}")
async def model_detail(model_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    return {
        "model_id": model_id,
        "model_name": f"Contract model {model_id}",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "result_schema": {"type": "object", "properties": {"score": {"type": "number"}}},
        "sandbox": True,
    }


@app.post("/models/{model_id}/invoke")
async def invoke(model_id: str, payload: dict[str, Any], authorization: str | None = Header(default=None)):
    _authorize(authorization)
    contract_case = str((payload.get("input_data") or {}).get("_contract_case") or "")
    if contract_case == "failure":
        raise HTTPException(status_code=500, detail="sandbox upstream failure")
    if contract_case == "timeout":
        await asyncio.sleep(2)
    if contract_case == "schema_change":
        return JSONResponse({"model_id": model_id, "status": "unexpected_status"})
    task_id = f"sandbox-{uuid.uuid4().hex[:12]}"
    async_mode = bool(payload.get("async_mode"))
    status = "submitted" if async_mode else "succeeded"
    result = {} if async_mode else {"score": 0.73, "result_type": "contract_fixture"}
    _tasks[task_id] = {"task_id": task_id, "status": "succeeded", "result": {"score": 0.73}}
    return {"model_id": model_id, "task_id": task_id, "status": status, "result": result}


@app.get("/tasks/{task_id}")
async def task_status(task_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="task not found")
    return {**_tasks[task_id], "updated_at": datetime.now(timezone.utc).isoformat()}


@app.get("/tasks/{task_id}/result")
async def task_result(task_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="task not found")
    return _tasks[task_id]


@app.get("/models/{model_id}/result-schema")
async def result_schema(model_id: str, authorization: str | None = Header(default=None)):
    _authorize(authorization)
    return {
        "model_id": model_id,
        "result_schema": {"type": "object", "properties": {"score": {"type": "number"}}},
    }
