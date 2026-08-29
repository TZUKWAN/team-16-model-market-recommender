"""Health check endpoint - GET /api/v1/health"""

from fastapi import APIRouter
from datetime import datetime, timezone
from app.core.config import get_settings
from app.services.llm_client import get_llm_client
from app.repositories.model_asset_repository import get_model_asset_repository
from app.integrations.model_market_client import get_model_market_client
from app.repositories.runtime_repository import get_runtime_repository
from app.services.auth_service import authentication_status
from app.integrations.model_market_contract import contract_evidence_status
from app.core.request_context import request_metrics
from app.services.recommender import get_model_recommendation_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return system health status."""
    settings = get_settings()
    llm_status = get_llm_client().status()
    model_repo = get_model_asset_repository()
    asset_stats = model_repo.stats()
    model_market_status = get_model_market_client().status()
    runtime_storage_ready, runtime_storage_detail = get_runtime_repository().integrity_check(
        cache_ttl_seconds=5.0
    )
    auth_status = authentication_status()
    contract_status = contract_evidence_status()
    dense_status = get_model_recommendation_service().dense_runtime_status()
    dense_ready = not dense_status["dense_required"] or dense_status["dense_available"]
    ready = runtime_storage_ready and dense_ready and (
        auth_status["auth_mode"] == "demo" or auth_status["production_auth_ready"]
    )
    return {
        "status": "healthy" if ready else "degraded",
        "version": settings.APP_VERSION,
        "app_name": settings.APP_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mock_mode": settings.ENABLE_MOCK,
        "official_dataset_loaded": (settings.DATA_DIR / "official" / "questions_all.jsonl").exists(),
        "model_market_connected": bool(model_market_status["connected"]),
        "model_market_adapter": model_market_status["adapter"],
        "model_market_demo_mode": bool(model_market_status["demo_mode"]),
        "model_market_configured": bool(model_market_status["configured"]),
        "model_market_status_message": model_market_status["message"],
        "model_market_contract_tested": contract_status["contract_tested"],
        "model_market_contract_hash": contract_status["contract_hash"],
        "model_market_real_connected": bool(model_market_status["connected"]),
        "request_metrics": request_metrics.snapshot(),
        "demo_result_mode": bool(model_market_status["demo_mode"]),
        "model_asset_repository_ready": asset_stats.total_models > 0,
        "model_asset_total": asset_stats.total_models,
        "model_asset_by_source": asset_stats.by_source,
        "model_asset_by_domain": asset_stats.by_domain,
        "model_asset_validation_issues": len(model_repo.validation_issues()),
        "runtime_storage": "sqlite",
        "runtime_storage_ready": runtime_storage_ready,
        "runtime_storage_integrity": runtime_storage_detail,
        "dense_runtime_ready": dense_ready,
        **dense_status,
        **auth_status,
        "llm_trace_enabled": settings.LLM_TRACE_ENABLED,
        **llm_status,
    }
