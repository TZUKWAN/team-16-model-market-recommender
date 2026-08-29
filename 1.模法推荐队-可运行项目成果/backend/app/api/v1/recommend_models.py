"""
Model recommendation endpoint - POST /api/v1/recommend-models
Uses ModelRecommendationService for real scoring and ranking.
"""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from app.schemas.recommendation import (
    RecommendModelsRequest, RecommendModelsResponse,
    RecommendedModel, ScoreBreakdown,
)
from app.core.security import get_current_user
from app.core.logging import get_logger
from app.core.errors import AppError
from app.schemas.auth import UserContext
from app.services.auth_service import get_auth_service
from app.services.audit_service import get_audit_service
from app.services.hybrid_retriever import DenseRetrievalUnavailableError
from app.services.recommender import (
    ModelCatalogUnavailableError,
    get_model_recommendation_service,
)
from app.services.feedback_service import get_feedback_service
from app.services.recommendation_version_store import (
    get_recommendation_version_store,
    recommendation_config_hash,
)

router = APIRouter()
logger = get_logger(__name__)

@router.post("/recommend-models", response_model=RecommendModelsResponse)
async def recommend_models(
    request: RecommendModelsRequest,
    current_user: UserContext = Depends(get_current_user),
):
    """Recommend models based on parsed demand."""
    parse_result = dict(request.parse_result or {})
    parse_result["model_source"] = request.model_source
    parse_result["user_role"] = current_user.role
    parse_result["institution_id"] = current_user.institution_id
    top_k = request.top_k or 5
    demo_top_k = request.demo_top_k
    prefer_api = request.prefer_api_available or False
    prefer_landing = request.prefer_landing_cases or False

    logger.info(
        "Recommending models (policy=%s, top_k=%s, demo_top_k=%s, api=%s, landing=%s)",
        request.model_source,
        top_k,
        demo_top_k,
        prefer_api,
        prefer_landing,
    )

    try:
        result = await run_in_threadpool(
            get_model_recommendation_service().recommend,
            parse_result=parse_result,
            top_k=top_k,
            demo_top_k=demo_top_k,
            prefer_api_available=prefer_api,
            prefer_landing_cases=prefer_landing,
        )
        auth_service = get_auth_service()
        filtered = [
            item for item in result.recommendations
            if auth_service.can_access_model(current_user, item.model_id, "recommend").allowed
        ]
        hidden = len(result.recommendations) - len(filtered)
        demo_filtered = [
            item for item in result.demo_references
            if auth_service.can_access_model(current_user, item.model_id, "recommend").allowed
        ]
        hidden_demo = len(result.demo_references) - len(demo_filtered)
        for rank, item in enumerate(filtered, start=1):
            item.rank = rank
        for rank, item in enumerate(demo_filtered, start=1):
            item.rank = rank
        main_catalog_label = "Demo主榜" if result.catalog_policy == "demo" else "官方模型"
        if hidden > 0 or hidden_demo > 0:
            result.summary = (
                f"{result.summary} 已按用户角色和机构权限过滤，"
                f"隐藏{hidden}个{main_catalog_label}和{hidden_demo}个Demo参考模型。"
            ).strip()
        result.recommendations = filtered
        result.demo_references = demo_filtered
        result.official_recommendation_count = (
            0 if result.catalog_policy == "demo" else len(filtered)
        )
        result.demo_reference_count = len(demo_filtered)
        get_feedback_service().record_recommendation_impressions(
            current_user,
            request_id=result.request_id,
            parse_result=parse_result,
            recommendations=[
                item.model_dump()
                for item in [*result.recommendations, *result.demo_references]
            ],
        )
        get_audit_service().record(
            "recommend_models",
            current_user,
            request_id=result.request_id,
            status="success",
            payload_summary={
                "intent": parse_result.get("intent", ""),
                "top_k": top_k,
                "visible_count": len(result.recommendations),
                "hidden_count": hidden,
                "model_ids": [item.model_id for item in result.recommendations],
                "demo_reference_count": len(result.demo_references),
                "hidden_demo_reference_count": hidden_demo,
                "demo_reference_ids": [item.model_id for item in result.demo_references],
                "catalog_policy": result.catalog_policy,
            },
        )
        logger.info(f"Recommended {len(result.recommendations)} models")

        # Persist this recommendation as an immutable version (F5.1).
        session_id = str(parse_result.get("session_id", "")) or f"sess_{current_user.user_id}"
        try:
            version_record = get_recommendation_version_store().save_version(
                session_id=session_id,
                request_id=result.request_id,
                parse_summary=parse_result,
                recommendations=[item.model_dump() for item in result.recommendations],
                config_hash=recommendation_config_hash(),
                raw_text=str(parse_result.get("raw_text", "")),
                idempotency_key=request.client_request_id,
                owner_user_id=current_user.user_id,
                institution_id=current_user.institution_id,
                legal_entity_id=current_user.legal_entity_id,
            )
            result.version_id = version_record.get("version_id", "")
            result.version_number = version_record.get("version_number", 0)
        except Exception as ve:
            logger.warning(f"Version persistence failed (non-blocking): {ve}")

        return result
    except DenseRetrievalUnavailableError as e:
        logger.error("Required dense retrieval is unavailable: %s", e.status.get("dense_error_code"))
        get_audit_service().record(
            "recommend_models",
            current_user,
            status="failed",
            payload_summary={
                "error": e.__class__.__name__,
                "dense_error_code": e.status.get("dense_error_code", ""),
                "retrieval_runtime_mode": e.status.get("retrieval_runtime_mode", ""),
            },
        )
        raise AppError(
            code="DENSE_RETRIEVAL_UNAVAILABLE",
            message="竞赛稠密检索模式尚未就绪，请检查 BGE-M3 依赖、权重和校验清单。",
            status_code=503,
            details={
                "dense_error_code": e.status.get("dense_error_code", ""),
                "retrieval_runtime_mode": e.status.get("retrieval_runtime_mode", ""),
            },
        ) from e
    except ModelCatalogUnavailableError as e:
        logger.error("Requested model catalog is unavailable: %s", e.source)
        get_audit_service().record(
            "recommend_models",
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
        logger.error(f"Recommendation failed: {e}", exc_info=True)
        get_audit_service().record(
            "recommend_models",
            current_user,
            status="fallback",
            payload_summary={"error": e.__class__.__name__},
        )
        # Return minimal fallback
        return RecommendModelsResponse(
            request_id="rec-fallback",
            summary="推荐服务暂时不可用，请稍后重试。",
            catalog_policy=request.model_source,
            demo_reference_status=(
                "unavailable" if request.model_source == "official_then_demo" else "not_requested"
            ),
        )
