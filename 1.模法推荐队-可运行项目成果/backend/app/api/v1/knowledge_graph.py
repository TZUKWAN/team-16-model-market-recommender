"""Knowledge graph endpoints for model-market evidence queries."""

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.schemas.knowledge_graph import (
    GraphMatchPathRequest,
    GraphMatchPathResponse,
    GraphNeighborhood,
    GraphOverview,
)
from app.services.knowledge_graph import get_knowledge_graph_service

router = APIRouter()
logger = get_logger(__name__)
_service = get_knowledge_graph_service()


@router.get("/graph/overview", response_model=GraphOverview)
async def get_graph_overview():
    """Return graph inventory and quality summary."""
    logger.info("Fetching knowledge graph overview")
    return _service.overview()


@router.get("/graph/model/{model_id}", response_model=GraphNeighborhood)
async def get_model_graph(model_id: str):
    """Return graph context for a model."""
    node_id = f"model:{model_id}"
    if not _service.has_node(node_id):
        raise HTTPException(status_code=404, detail=f"Model graph node {model_id} not found")
    return _service.model_neighborhood(model_id)


@router.get("/graph/scenario/{scenario_id}", response_model=GraphNeighborhood)
async def get_scenario_graph(scenario_id: str):
    """Return graph context for a business scenario name or slug."""
    node_id = _service.scenario_node_id(scenario_id)
    if not _service.has_node(node_id):
        raise HTTPException(status_code=404, detail=f"Scenario graph node {scenario_id} not found")
    return _service.scenario_neighborhood(scenario_id)


@router.get("/graph/node/{node_id}", response_model=GraphNeighborhood)
async def get_node_graph(node_id: str):
    """Return the 1-hop neighborhood for any graph node (used for drilldown)."""
    if not _service.has_node(node_id):
        raise HTTPException(status_code=404, detail=f"Graph node {node_id} not found")
    return _service.neighborhood(node_id)


@router.post("/graph/match-path", response_model=GraphMatchPathResponse)
async def match_graph_path(request: GraphMatchPathRequest):
    """Match parsed demand to graph evidence nodes and edges."""
    if request.model_id:
        node_id = f"model:{request.model_id}"
        if not _service.has_node(node_id):
            raise HTTPException(status_code=404, detail=f"Model graph node {request.model_id} not found")
    return _service.match_path(
        parse_result=request.parse_result,
        model_id=request.model_id,
        max_edges=request.max_edges,
    )
