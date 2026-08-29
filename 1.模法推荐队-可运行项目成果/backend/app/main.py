"""
FastAPI application entry point for the Model Market Assistant.
"""

from contextlib import asynccontextmanager
import json
import re
import time
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.core.errors import register_error_handlers
from app.api.v1.router import api_v1_router
from app.core.request_context import correlation_id_var, request_id_var, request_metrics
from app.core.input_limits import json_depth

settings = get_settings()
logger = get_logger(__name__)
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup/shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Mock mode: {settings.ENABLE_MOCK}")
    from app.services.hybrid_retriever import DenseRetrievalUnavailableError
    from app.services.recommender import get_model_recommendation_service

    try:
        dense_status = await run_in_threadpool(
            get_model_recommendation_service().warmup_dense_runtime
        )
        logger.info(
            "Dense retrieval readiness: mode=%s requested=%s required=%s available=%s dimension=%s",
            dense_status["retrieval_runtime_mode"],
            dense_status["dense_requested"],
            dense_status["dense_required"],
            dense_status["dense_available"],
            dense_status["dense_embedding_dimension"],
        )
    except DenseRetrievalUnavailableError as exc:
        logger.error(
            "Required dense retrieval failed startup warmup: %s",
            exc.status.get("dense_error_code", "unknown"),
        )
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="银行模型市场智能推荐助手 - Bank Model Market Intelligent Recommendation Assistant",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def request_observability(request, call_next):
    safe_id = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
    incoming_request_id = request.headers.get("X-Request-ID", "")
    incoming_correlation_id = request.headers.get("X-Correlation-ID", "")
    request_id = incoming_request_id if safe_id.fullmatch(incoming_request_id) else str(uuid.uuid4())
    correlation_id = (
        incoming_correlation_id
        if safe_id.fullmatch(incoming_correlation_id)
        else request_id
    )
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    request_token = request_id_var.set(request_id)
    correlation_token = correlation_id_var.set(correlation_id)
    started = time.perf_counter()
    status_code = 500
    try:
        response = None
        content_length = request.headers.get("content-length", "")
        if content_length:
            try:
                if int(content_length) > settings.REQUEST_MAX_BODY_BYTES:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "request body exceeds configured size limit"},
                    )
            except ValueError:
                response = JSONResponse(status_code=400, content={"detail": "invalid content-length header"})
        if response is None and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body = await request.body()
            if len(body) > settings.REQUEST_MAX_BODY_BYTES:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "request body exceeds configured size limit"},
                )
            elif body and "application/json" in request.headers.get("content-type", "").lower():
                try:
                    payload = json.loads(body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                if payload is not None and json_depth(payload) > settings.JSON_MAX_DEPTH:
                    response = JSONResponse(
                        status_code=400,
                        content={"detail": "JSON nesting exceeds configured depth limit"},
                    )
        if response is None:
            response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        request_metrics.record(status_code)
        logger.info(
            "http_request method=%s path=%s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
        )
        request_id_var.reset(request_token)
        correlation_id_var.reset(correlation_token)

# --- Error handlers ---
register_error_handlers(app)

# --- API routes ---
app.include_router(api_v1_router, prefix=settings.API_PREFIX)

# --- Root endpoint ---
@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
    )
