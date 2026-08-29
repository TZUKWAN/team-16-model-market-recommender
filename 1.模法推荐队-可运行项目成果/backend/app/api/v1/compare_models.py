"""Model comparison endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.schemas.auth import UserContext
from app.schemas.comparison import CompareModelsRequest, CompareModelsResponse
from app.services.auth_service import get_auth_service
from app.services.model_comparison_service import ModelComparisonService

router = APIRouter()
_service = ModelComparisonService()


@router.post("/compare-models", response_model=CompareModelsResponse)
async def compare_models(
    request: CompareModelsRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Compare selected models and estimate expected effect."""
    auth = get_auth_service()
    allowed_ids = [
        model_id for model_id in request.model_ids
        if auth.can_access_model(current_user, model_id, "recommend").allowed
    ]
    if len(allowed_ids) < 2:
        raise HTTPException(status_code=403, detail="至少需要选择2个当前用户可访问的模型进行对比")
    response = _service.compare(allowed_ids, request.parse_result)
    if len(response.items) < 2:
        raise HTTPException(status_code=404, detail="可对比模型不足2个")
    return response