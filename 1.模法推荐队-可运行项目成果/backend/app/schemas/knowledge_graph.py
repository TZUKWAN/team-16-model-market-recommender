"""Schemas for the lightweight model-market knowledge graph."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """A typed entity in the model-market knowledge graph."""

    node_id: str
    node_type: str
    name: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A directed relationship between two graph entities."""

    edge_id: str
    source: str
    target: str
    relation_type: str
    weight: float = 1.0
    evidence: dict[str, Any] = Field(default_factory=dict)


class GraphOverview(BaseModel):
    """Inventory and quality summary for a built graph snapshot."""

    node_count: int
    edge_count: int
    node_type_counts: dict[str, int] = Field(default_factory=dict)
    relation_type_counts: dict[str, int] = Field(default_factory=dict)
    isolated_node_count: int = 0
    model_count: int = 0
    official_model_count: int = 0
    demo_model_count: int = 0


class GraphNeighborhood(BaseModel):
    """Nodes and edges directly connected to one graph node."""

    center_node_id: str
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class GraphMatchPathRequest(BaseModel):
    """Request to match parsed demand against graph evidence paths."""

    parse_result: dict[str, Any] = Field(default_factory=dict)
    model_id: str = ""
    max_edges: int = Field(default=80, ge=1, le=300)


class GraphMatchPathResponse(BaseModel):
    """Graph evidence matched between a demand and optional model."""

    model_id: str = ""
    matched_node_ids: list[str] = Field(default_factory=list)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    summary: str = ""


class KnowledgeGraphSnapshot(BaseModel):
    """A complete in-memory graph snapshot."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    overview: GraphOverview
