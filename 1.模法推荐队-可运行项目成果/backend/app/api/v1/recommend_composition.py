"""
Model composition endpoint - POST /api/v1/recommend-composition
Uses CompositionPlanner service for real composition planning.
"""

from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.schemas.composition import (
    RecommendCompositionRequest, RecommendCompositionResponse,
)
from app.schemas.auth import UserContext
from app.core.logging import get_logger
from app.core.errors import AppError
from app.services.audit_service import get_audit_service
from app.services.composition_planner import CompositionPlanner
from app.services.composition_executor import CompositionExecutor
from app.services.recommender import ModelCatalogUnavailableError

router = APIRouter()
logger = get_logger(__name__)

_planner = CompositionPlanner()
_executor = CompositionExecutor()


@router.post("/recommend-composition", response_model=RecommendCompositionResponse)
async def recommend_composition(
    request: RecommendCompositionRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Recommend a model composition plan."""
    parse_result = dict(request.parse_result or {})
    parse_result["model_source"] = request.model_source
    parse_result["permitted_domains"] = list(current_user.permitted_domains)
    parse_result["user_role"] = current_user.role
    top_k = request.top_k or 3

    logger.info(f"Planning composition (top_k={top_k})")

    try:
        result = _planner.plan(
            parse_result=parse_result,
            top_k=top_k,
        )
        result.execution_result = _executor.execute_demo(
            composition=result,
            parse_result=parse_result,
        )
        get_audit_service().record(
            "recommend_composition",
            current_user,
            request_id=result.composition_id,
            status="success",
            payload_summary={
                "scenario": result.scenario,
                "node_count": len(result.nodes),
                "execution_status": result.execution_result.status if result.execution_result else "",
                "model_source": request.model_source,
            },
        )
        logger.info(f"Planned composition with {len(result.nodes)} nodes")
        return result
    except ModelCatalogUnavailableError as e:
        logger.error("Requested composition model catalog is unavailable: %s", e.source)
        get_audit_service().record(
            "recommend_composition",
            current_user,
            status="failed",
            payload_summary={"error": e.__class__.__name__, "model_source": e.source},
        )
        raise AppError(
            code="MODEL_CATALOG_UNAVAILABLE",
            message=f"模型目录 {e.source} 当前不可用，请检查数据加载状态。",
            status_code=503,
            details={"model_source": e.source},
        ) from e
    except Exception as e:
        logger.error(f"Composition planning failed: {e}", exc_info=True)
        get_audit_service().record(
            "recommend_composition",
            current_user,
            status="fallback",
            payload_summary={"error": e.__class__.__name__},
        )
        # Return minimal fallback
        return RecommendCompositionResponse(
            composition_id="COMP_FALLBACK",
            composition_name="基础方案",
            scenario="通用",
            total_score=30.0,
            usage_guide=["组合编排服务暂时不可用，请稍后重试。"],
        )
