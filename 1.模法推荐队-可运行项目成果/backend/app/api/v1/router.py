"""
Main API router - aggregates all v1 endpoints under /api/v1.
"""

from fastapi import APIRouter
from .health import router as health_router
from .parse_demand import router as parse_router
from .recommend_models import router as recommend_router
from .recommend_composition import router as composition_router
from .model_detail import router as model_router
from .reports import router as reports_router
from .evaluation import router as evaluation_router
from .official_evaluation import router as official_evaluation_router
from .knowledge_graph import router as graph_router
from .model_inference import router as inference_router
from .audit import router as audit_router
from .compare_models import router as compare_router
from .feedback import router as feedback_router
from .scenarios import router as scenarios_router
from .surveys import router as surveys_router
from .recommendation_versions import router as version_router

api_v1_router = APIRouter()

# Include all sub-routers
api_v1_router.include_router(health_router, tags=["Health"])
api_v1_router.include_router(parse_router, tags=["Demand Parsing"])
api_v1_router.include_router(recommend_router, tags=["Recommendation"])
api_v1_router.include_router(composition_router, tags=["Composition"])
api_v1_router.include_router(model_router, tags=["Models"])
api_v1_router.include_router(reports_router, tags=["Reports"])
api_v1_router.include_router(evaluation_router, tags=["Evaluation"])
api_v1_router.include_router(official_evaluation_router, tags=["Official Evaluation"])
api_v1_router.include_router(graph_router, tags=["Knowledge Graph"])
api_v1_router.include_router(inference_router, tags=["Model Inference"])
api_v1_router.include_router(audit_router, tags=["Audit"])
api_v1_router.include_router(compare_router, tags=["Model Comparison"])
api_v1_router.include_router(feedback_router, tags=["Feedback"])
api_v1_router.include_router(scenarios_router, tags=["Scenarios"])
api_v1_router.include_router(surveys_router, tags=["Human Surveys"])
api_v1_router.include_router(version_router, tags=["Recommendation Versions"])
