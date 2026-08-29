"""Lightweight knowledge graph builder for model-market assets.

The graph is intentionally file-backed and deterministic. It gives recommendation
explanations and future graph APIs a real data layer without requiring Neo4j or a
separate graph database during competition/demo runs.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.repositories.model_asset_repository import ModelAssetRepository
from app.schemas.knowledge_graph import (
    GraphEdge,
    GraphMatchPathResponse,
    GraphNeighborhood,
    GraphNode,
    GraphOverview,
    KnowledgeGraphSnapshot,
)
from app.services.data_loader import load_composition_templates


class KnowledgeGraphService:
    """Build and query the lightweight model-market knowledge graph."""

    def __init__(
        self,
        repository: ModelAssetRepository | None = None,
        templates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.repository = repository or ModelAssetRepository()
        self.templates = templates if templates is not None else load_composition_templates()
        self._snapshot: KnowledgeGraphSnapshot | None = None

    def build(self, force: bool = False) -> KnowledgeGraphSnapshot:
        """Build or return a cached deterministic graph snapshot."""
        if self._snapshot is not None and not force:
            return self._snapshot

        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        models = sorted(self.repository.list_models(), key=lambda item: str(item.get("model_id", "")))

        for model in models:
            self._add_model_subgraph(model, nodes, edges)

        self._add_composition_templates(nodes, edges)
        self._add_model_compatibility_edges(models, edges)

        overview = self._build_overview(nodes, edges)
        self._snapshot = KnowledgeGraphSnapshot(
            nodes=sorted(nodes.values(), key=lambda node: node.node_id),
            edges=sorted(edges.values(), key=lambda edge: edge.edge_id),
            overview=overview,
        )
        return self._snapshot

    def overview(self) -> GraphOverview:
        """Return graph inventory and quality metrics."""
        return self.build().overview

    def neighborhood(self, node_id: str) -> GraphNeighborhood:
        """Return nodes and edges connected to a graph node."""
        snapshot = self.build()
        edge_list = [
            edge
            for edge in snapshot.edges
            if edge.source == node_id or edge.target == node_id
        ]
        connected_ids = {node_id}
        for edge in edge_list:
            connected_ids.add(edge.source)
            connected_ids.add(edge.target)
        node_list = [node for node in snapshot.nodes if node.node_id in connected_ids]
        return GraphNeighborhood(
            center_node_id=node_id,
            nodes=sorted(node_list, key=lambda node: node.node_id),
            edges=sorted(edge_list, key=lambda edge: edge.edge_id),
        )

    def model_neighborhood(self, model_id: str) -> GraphNeighborhood:
        """Return graph context for a model asset."""
        return self.neighborhood(f"model:{model_id}")

    def scenario_neighborhood(self, scenario_id: str) -> GraphNeighborhood:
        """Return graph context for a scenario name or scenario node id."""
        return self.neighborhood(self.scenario_node_id(scenario_id))

    def scenario_node_id(self, scenario_id: str) -> str:
        """Return normalized graph node id for a scenario name or node id."""
        return scenario_id if scenario_id.startswith("scenario:") else f"scenario:{self._slug(scenario_id)}"

    def has_node(self, node_id: str) -> bool:
        """Return whether a node exists in the graph snapshot."""
        snapshot = self.build()
        return any(node.node_id == node_id for node in snapshot.nodes)

    def match_path(
        self,
        parse_result: dict[str, Any],
        model_id: str = "",
        max_edges: int = 80,
    ) -> GraphMatchPathResponse:
        """Match parsed demand fields to graph nodes and return evidence edges."""
        snapshot = self.build()
        node_by_id = {node.node_id: node for node in snapshot.nodes}
        matched_node_ids = self._match_parse_result_nodes(parse_result, node_by_id)
        selected_edges: list[GraphEdge] = []

        model_node_id = f"model:{model_id}" if model_id else ""
        if model_node_id and model_node_id in node_by_id:
            direct_edges = [
                edge
                for edge in snapshot.edges
                if edge.source == model_node_id and edge.target in matched_node_ids
            ]
            selected_edges.extend(direct_edges)
            if not direct_edges:
                selected_edges.extend(
                    edge
                    for edge in snapshot.edges
                    if edge.source == model_node_id or edge.target == model_node_id
                )
        else:
            selected_edges.extend(
                edge
                for edge in snapshot.edges
                if edge.source in matched_node_ids or edge.target in matched_node_ids
            )

        if len(selected_edges) > max_edges:
            selected_edges = sorted(selected_edges, key=lambda edge: (-edge.weight, edge.edge_id))[:max_edges]
        else:
            selected_edges = sorted(selected_edges, key=lambda edge: edge.edge_id)

        selected_node_ids = set(matched_node_ids)
        if model_node_id and model_node_id in node_by_id:
            selected_node_ids.add(model_node_id)
        for edge in selected_edges:
            selected_node_ids.add(edge.source)
            selected_node_ids.add(edge.target)

        nodes = sorted(
            [node_by_id[node_id] for node_id in selected_node_ids if node_id in node_by_id],
            key=lambda node: node.node_id,
        )
        # Include the target model node in the highlight set so the full demand→model path is visible.
        highlight_ids = set(matched_node_ids)
        if model_node_id and model_node_id in node_by_id:
            highlight_ids.add(model_node_id)
        matched = sorted(node_id for node_id in highlight_ids if node_id in node_by_id)
        summary = (
            f"匹配到 {len(matched)} 个需求图谱节点，返回 {len(nodes)} 个节点和 {len(selected_edges)} 条证据边。"
        )
        return GraphMatchPathResponse(
            model_id=model_id,
            matched_node_ids=matched,
            nodes=nodes,
            edges=selected_edges,
            summary=summary,
        )

    def export_jsonl(self, nodes_path: Path, edges_path: Path) -> KnowledgeGraphSnapshot:
        """Write graph nodes and edges as JSONL files."""
        snapshot = self.build()
        nodes_path.parent.mkdir(parents=True, exist_ok=True)
        edges_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_jsonl(nodes_path, snapshot.nodes)
        self._write_jsonl(edges_path, snapshot.edges)
        return snapshot

    def _add_model_subgraph(
        self,
        model: dict[str, Any],
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> None:
        model_id = str(model.get("model_id", "")).strip()
        if not model_id:
            return

        model_node_id = f"model:{model_id}"
        self._add_node(
            nodes,
            GraphNode(
                node_id=model_node_id,
                node_type="model",
                name=str(model.get("model_name") or model.get("canonical_name") or model_id),
                properties={
                    "model_id": model_id,
                    "domain": model.get("domain", ""),
                    "source": model.get("source", ""),
                    "api_available": bool(model.get("api_available", False)),
                    "asset_status": model.get("asset_status", ""),
                    "permission_scope": model.get("permission_scope", ""),
                    "business_stage": self._as_list(model.get("business_stage")),
                },
            ),
        )

        relation_specs = [
            ("business_scenario", "scenario", "applies_to", 0.95),
            ("business_stage", "stage", "belongs_to_stage", 0.90),
            ("customer_segment", "segment", "targets_segment", 0.80),
            ("model_capability", "capability", "has_capability", 0.90),
            ("tags", "tag", "has_tag", 0.70),
            ("input_fields_required", "field", "requires", 1.00),
            ("input_fields_optional", "field", "optional_requires", 0.55),
            ("output_fields", "output", "outputs", 1.00),
        ]
        for field_name, node_type, relation_type, weight in relation_specs:
            for raw_value in self._as_list(model.get(field_name)):
                related_node_id = f"{node_type}:{self._slug(raw_value)}"
                self._add_node(
                    nodes,
                    GraphNode(
                        node_id=related_node_id,
                        node_type=node_type,
                        name=raw_value,
                        properties={"source_field": field_name},
                    ),
                )
                self._add_edge(
                    edges,
                    source=model_node_id,
                    target=related_node_id,
                    relation_type=relation_type,
                    weight=weight,
                    evidence={"model_id": model_id, "field": field_name, "value": raw_value},
                )

    def _add_composition_templates(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> None:
        for template in sorted(self.templates, key=lambda item: str(item.get("template_id", ""))):
            template_id = str(template.get("template_id") or template.get("id") or template.get("name") or "").strip()
            if not template_id:
                continue
            composition_node_id = f"composition:{self._slug(template_id)}"
            self._add_node(
                nodes,
                GraphNode(
                    node_id=composition_node_id,
                    node_type="composition",
                    name=str(template.get("name") or template_id),
                    properties={
                        "template_id": template_id,
                        "complexity": template.get("complexity", ""),
                        "typical_model_count": template.get("typical_model_count", ""),
                        "description": template.get("description", ""),
                    },
                ),
            )

            for scenario in self._as_list(template.get("applicable_scenarios")):
                scenario_node_id = f"scenario:{self._slug(scenario)}"
                self._add_node(
                    nodes,
                    GraphNode(
                        node_id=scenario_node_id,
                        node_type="scenario",
                        name=scenario,
                        properties={"source_field": "composition.applicable_scenarios"},
                    ),
                )
                self._add_edge(
                    edges,
                    source=composition_node_id,
                    target=scenario_node_id,
                    relation_type="recommends_for_scenario",
                    weight=0.85,
                    evidence={"template_id": template_id, "scenario": scenario},
                )

            pipeline_capabilities: list[tuple[str, list[str]]] = []
            for stage in template.get("stages") or []:
                if not isinstance(stage, dict):
                    continue
                stage_key = str(stage.get("stage") or stage.get("name") or "").strip()
                if stage_key:
                    stage_node_id = f"stage:{self._slug(stage_key)}"
                    self._add_node(
                        nodes,
                        GraphNode(
                            node_id=stage_node_id,
                            node_type="stage",
                            name=str(stage.get("name") or stage_key),
                            properties={"stage": stage_key, "template_id": template_id},
                        ),
                    )
                    self._add_edge(
                        edges,
                        source=composition_node_id,
                        target=stage_node_id,
                        relation_type="has_stage",
                        weight=0.80,
                        evidence={"template_id": template_id, "stage": stage_key},
                    )

                required_capabilities = self._as_list(stage.get("required_models"))
                optional_capabilities = self._as_list(stage.get("optional_models"))
                for capability in required_capabilities:
                    self._link_composition_capability(
                        composition_node_id, template_id, stage_key, capability, True, nodes, edges
                    )
                for capability in optional_capabilities:
                    self._link_composition_capability(
                        composition_node_id, template_id, stage_key, capability, False, nodes, edges
                    )
                stage_capabilities = required_capabilities + optional_capabilities
                if stage_capabilities:
                    pipeline_capabilities.append((stage_key, stage_capabilities))

            for (source_stage, source_caps), (target_stage, target_caps) in zip(
                pipeline_capabilities,
                pipeline_capabilities[1:],
                strict=False,
            ):
                for source_capability in source_caps:
                    for target_capability in target_caps:
                        if source_capability == target_capability:
                            continue
                        self._add_edge(
                            edges,
                            source=f"capability:{self._slug(source_capability)}",
                            target=f"capability:{self._slug(target_capability)}",
                            relation_type="can_feed",
                            weight=0.65,
                            evidence={
                                "template_id": template_id,
                                "source_stage": source_stage,
                                "target_stage": target_stage,
                            },
                        )

    def _link_composition_capability(
        self,
        composition_node_id: str,
        template_id: str,
        stage_key: str,
        capability: str,
        required: bool,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> None:
        capability_node_id = f"capability:{self._slug(capability)}"
        self._add_node(
            nodes,
            GraphNode(
                node_id=capability_node_id,
                node_type="capability",
                name=capability,
                properties={"source_field": "composition.stage.required_models"},
            ),
        )
        self._add_edge(
            edges,
            source=composition_node_id,
            target=capability_node_id,
            relation_type="requires_capability" if required else "optional_capability",
            weight=0.90 if required else 0.60,
            evidence={"template_id": template_id, "stage": stage_key, "capability": capability},
        )

    def _add_model_compatibility_edges(
        self,
        models: list[dict[str, Any]],
        edges: dict[str, GraphEdge],
    ) -> None:
        input_index: dict[str, list[tuple[str, str]]] = {}
        for model in models:
            model_id = str(model.get("model_id", "")).strip()
            if not model_id:
                continue
            for field in self._as_list(model.get("input_fields_required")):
                input_index.setdefault(self._slug(field), []).append((model_id, "required"))
            for field in self._as_list(model.get("input_fields_optional")):
                input_index.setdefault(self._slug(field), []).append((model_id, "optional"))

        for producer in models:
            producer_id = str(producer.get("model_id", "")).strip()
            if not producer_id:
                continue
            for output_field in self._as_list(producer.get("output_fields")):
                for consumer_id, input_kind in input_index.get(self._slug(output_field), []):
                    if consumer_id == producer_id:
                        continue
                    self._add_edge(
                        edges,
                        source=f"model:{producer_id}",
                        target=f"model:{consumer_id}",
                        relation_type="can_feed",
                        weight=0.70 if input_kind == "required" else 0.45,
                        evidence={
                            "output_field": output_field,
                            "consumer_input_kind": input_kind,
                        },
                    )

    def _build_overview(
        self,
        nodes: dict[str, GraphNode],
        edges: dict[str, GraphEdge],
    ) -> GraphOverview:
        node_type_counts = Counter(node.node_type for node in nodes.values())
        relation_type_counts = Counter(edge.relation_type for edge in edges.values())
        connected_node_ids: set[str] = set()
        for edge in edges.values():
            connected_node_ids.add(edge.source)
            connected_node_ids.add(edge.target)
        isolated_node_count = len([node_id for node_id in nodes if node_id not in connected_node_ids])

        model_nodes = [node for node in nodes.values() if node.node_type == "model"]
        official_model_count = len(
            [node for node in model_nodes if node.properties.get("source") == "official"]
        )
        demo_model_count = len([node for node in model_nodes if node.properties.get("source") == "demo"])

        return GraphOverview(
            node_count=len(nodes),
            edge_count=len(edges),
            node_type_counts=dict(sorted(node_type_counts.items())),
            relation_type_counts=dict(sorted(relation_type_counts.items())),
            isolated_node_count=isolated_node_count,
            model_count=len(model_nodes),
            official_model_count=official_model_count,
            demo_model_count=demo_model_count,
        )

    def _match_parse_result_nodes(
        self,
        parse_result: dict[str, Any],
        node_by_id: dict[str, GraphNode],
    ) -> set[str]:
        matched: set[str] = set()
        field_to_types = {
            "business_scenario": ("scenario", "tag"),
            "business_stage": ("stage", "tag"),
            "customer_segment": ("segment", "tag"),
            "expected_outputs": ("output", "tag", "capability"),
            "data_conditions": ("field", "tag"),
            "tags": ("tag", "capability", "stage", "segment"),
            "tag_names": ("tag", "capability", "stage", "segment"),
            "intent": ("tag", "capability"),
            "domain": ("tag",),
        }
        for field_name, node_types in field_to_types.items():
            for value in self._as_list(parse_result.get(field_name)):
                slug = self._slug(value)
                for node_type in node_types:
                    node_id = f"{node_type}:{slug}"
                    if node_id in node_by_id:
                        matched.add(node_id)

                lowered = value.strip().lower()
                for node in node_by_id.values():
                    if node.node_type not in node_types:
                        continue
                    if lowered and lowered == node.name.strip().lower():
                        matched.add(node.node_id)
        return matched

    @staticmethod
    def _add_node(nodes: dict[str, GraphNode], node: GraphNode) -> None:
        if node.node_id not in nodes:
            nodes[node.node_id] = node

    @classmethod
    def _add_edge(
        cls,
        edges: dict[str, GraphEdge],
        source: str,
        target: str,
        relation_type: str,
        weight: float,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        edge_id = cls._edge_id(source, target, relation_type)
        if edge_id not in edges:
            edges[edge_id] = GraphEdge(
                edge_id=edge_id,
                source=source,
                target=target,
                relation_type=relation_type,
                weight=weight,
                evidence=evidence or {},
            )

    @staticmethod
    def _edge_id(source: str, target: str, relation_type: str) -> str:
        return f"edge:{relation_type}:{source}->{target}"

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple | set):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _slug(value: str) -> str:
        text = str(value).strip().lower()
        text = re.sub(r"\s+", "_", text)
        text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text)
        text = text.strip("_")
        return text or "unknown"

    @staticmethod
    def _write_jsonl(path: Path, records: list[GraphNode] | list[GraphEdge]) -> None:
        with path.open("w", encoding="utf-8") as fp:
            for record in records:
                if hasattr(record, "model_dump"):
                    payload = record.model_dump()
                else:
                    payload = record.dict()
                fp.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


_knowledge_graph_service: KnowledgeGraphService | None = None


def get_knowledge_graph_service() -> KnowledgeGraphService:
    """Return singleton knowledge graph service."""
    global _knowledge_graph_service
    if _knowledge_graph_service is None:
        _knowledge_graph_service = KnowledgeGraphService()
    return _knowledge_graph_service


def reset_knowledge_graph_service_for_tests() -> None:
    """Reset singleton knowledge graph service in tests."""
    global _knowledge_graph_service
    _knowledge_graph_service = None
