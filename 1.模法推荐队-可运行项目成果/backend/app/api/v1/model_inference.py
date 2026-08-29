"""Model invocation endpoints backed by the configured model-market adapter."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.core.logging import get_logger
from app.integrations.base import ModelMarketNotConfiguredError, ModelMarketUpstreamError
from app.integrations.model_market_client import get_model_market_client
from app.schemas.auth import UserContext
from app.schemas.inference import (
    ModelInvokeRequest,
    ModelInvokeResponse,
    ModelResultResponse,
    ModelResultSchemaResponse,
    ModelTaskStatusResponse,
)
from app.services.audit_service import get_audit_service
from app.services.auth_service import get_auth_service

router = APIRouter()
logger = get_logger(__name__)


@router.post("/models/{model_id}/invoke", response_model=ModelInvokeResponse)
async def invoke_model(
    model_id: str,
    request: ModelInvokeRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Invoke a model through the configured model-market adapter."""
    auth_service = get_auth_service()
    decision = auth_service.can_access_model(current_user, model_id, "invoke")
    if not decision.allowed:
        get_audit_service().record(
            "model_invoke",
            current_user,
            model_id=model_id,
            status="denied",
            payload_summary={"reason": decision.reason},
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        payload = {
            "input_data": request.input_data,
            "async_mode": request.async_mode,
            "request_context": {
                **request.request_context,
                "user_id": current_user.user_id,
                "institution_id": current_user.institution_id,
                "legal_entity_id": current_user.legal_entity_id,
            },
        }
        result = await get_model_market_client().invoke_model(model_id, payload)
        auth_service.register_task(result.get("task_id", ""), model_id, current_user)
        get_audit_service().record(
            "model_invoke",
            current_user,
            model_id=model_id,
            task_id=result.get("task_id", ""),
            status=result.get("status", "success"),
            result_type=(result.get("result") or {}).get("result_type", ""),
            payload_summary={
                "async_mode": request.async_mode,
                "input_keys": list(request.input_data.keys()),
                "demo_data": result.get("demo_data", False),
            },
        )
        return ModelInvokeResponse(**result)
    except ModelMarketNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelMarketUpstreamError as exc:
        logger.warning("Model invocation upstream error for %s: %s", model_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=ModelTaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get model invocation task status."""
    decision = get_auth_service().can_view_task(current_user, task_id)
    if not decision.allowed:
        get_audit_service().record(
            "task_status_view",
            current_user,
            task_id=task_id,
            status="denied",
            payload_summary={"reason": decision.reason},
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        result = await get_model_market_client().get_task_status(task_id)
        get_audit_service().record(
            "task_status_view",
            current_user,
            task_id=task_id,
            status="success",
            payload_summary={"task_status": result.get("status", "")},
        )
        return ModelTaskStatusResponse(**result)
    except ModelMarketNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelMarketUpstreamError as exc:
        logger.warning("Model task status upstream error for %s: %s", task_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/result", response_model=ModelResultResponse)
async def get_task_result(
    task_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get model invocation task result."""
    decision = get_auth_service().can_view_task(current_user, task_id)
    if not decision.allowed:
        get_audit_service().record(
            "model_result_view",
            current_user,
            task_id=task_id,
            status="denied",
            payload_summary={"reason": decision.reason},
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        result = await get_model_market_client().get_model_result(task_id)
        get_audit_service().record(
            "model_result_view",
            current_user,
            task_id=task_id,
            status="success",
            result_type=(result.get("result") or {}).get("result_type", ""),
            payload_summary={
                "task_status": result.get("status", ""),
                "demo_data": result.get("demo_data", False),
            },
        )
        return ModelResultResponse(**result)
    except ModelMarketNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelMarketUpstreamError as exc:
        logger.warning("Model result upstream error for %s: %s", task_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/models/{model_id}/result-schema", response_model=ModelResultSchemaResponse)
async def get_model_result_schema(
    model_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get model result schema from the configured adapter."""
    decision = get_auth_service().can_access_model(current_user, model_id, "view_result")
    if not decision.allowed:
        get_audit_service().record(
            "model_result_schema_view",
            current_user,
            model_id=model_id,
            status="denied",
            payload_summary={"reason": decision.reason},
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    try:
        result = await get_model_market_client().get_result_schema(model_id)
        get_audit_service().record(
            "model_result_schema_view",
            current_user,
            model_id=model_id,
            status="success",
            payload_summary={"demo_data": result.get("demo_data", False)},
        )
        return ModelResultSchemaResponse(**result)
    except ModelMarketNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelMarketUpstreamError as exc:
        logger.warning("Model result schema upstream error for %s: %s", model_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
