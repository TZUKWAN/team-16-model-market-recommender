"""
Model detail endpoint - GET /api/v1/models/{model_id}
Uses ModelAssetRepository to serve normalized model metadata.
"""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.schemas.model import ModelMetadata
from app.schemas.auth import UserContext
from app.core.logging import get_logger
from app.repositories.model_asset_repository import get_model_asset_repository
from app.services.audit_service import get_audit_service
from app.services.auth_service import get_auth_service

router = APIRouter()
logger = get_logger(__name__)
repository = get_model_asset_repository()


@router.get("/models/{model_id}", response_model=ModelMetadata)
async def get_model_detail(
    model_id: str,
    current_user: UserContext = Depends(get_current_user),
):
    """Get detailed metadata for a specific model."""
    logger.info(f"Fetching model detail: {model_id}")

    model = repository.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    decision = get_auth_service().can_access_model(current_user, model_id, "view_result")
    if not decision.allowed:
        get_audit_service().record(
            "model_detail_view",
            current_user,
            model_id=model_id,
            status="denied",
            payload_summary={"reason": decision.reason},
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    get_audit_service().record(
        "model_detail_view",
        current_user,
        model_id=model_id,
        status="success",
        payload_summary={"domain": model.get("domain", "")},
    )
    return ModelMetadata(**model)
