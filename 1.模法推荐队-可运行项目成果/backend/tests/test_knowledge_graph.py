"""Tests for the lightweight model-market knowledge graph."""

from pathlib import Path

from app.services.knowledge_graph import KnowledgeGraphService


def test_graph_builds_from_demo_and_official_assets():
    service = KnowledgeGraphService()
    snapshot = service.build()
    node_ids = {node.node_id for node in snapshot.nodes}

    assert snapshot.overview.node_count > 0
    assert snapshot.overview.edge_count > 0
    assert snapshot.overview.model_count >= 165
    assert snapshot.overview.official_model_count >= 60
    assert snapshot.overview.demo_model_count >= 105
    assert "model:MKT_001" in node_ids
    assert "model:RISK_001" in node_ids
    assert "model:OFFICIAL_001" in node_ids


def test_key_marketing_model_has_traceable_graph_context():
    service = KnowledgeGraphService()
    neighborhood = service.model_neighborhood("MKT_001")
    edge_types = {edge.relation_type for edge in neighborhood.edges}
    target_ids = {edge.target for edge in neighborhood.edges}

    assert "applies_to" in edge_types
    assert "has_tag" in edge_types
    assert "requires" in edge_types
    assert "outputs" in edge_types
    assert "scenario:县域新客首贷营销" in target_ids
    assert "field:customer_profile" in target_ids
    assert "output:conversion_probability" in target_ids


def test_composition_templates_are_linked_to_capabilities():
    service = KnowledgeGraphService()
    snapshot = service.build()
    edge_pairs = {(edge.source, edge.target, edge.relation_type) for edge in snapshot.edges}

    assert (
        "composition:tmpl_002",
        "capability:conversion_prediction",
        "requires_capability",
    ) in edge_pairs
    assert (
        "composition:tmpl_001",
        "capability:anti_fraud",
        "requires_capability",
    ) in edge_pairs
    assert any(edge.relation_type == "can_feed" for edge in snapshot.edges)


def test_graph_export_writes_jsonl(tmp_path: Path):
    nodes_path = tmp_path / "graph_nodes.jsonl"
    edges_path = tmp_path / "graph_edges.jsonl"
    service = KnowledgeGraphService()

    snapshot = service.export_jsonl(nodes_path, edges_path)

    assert nodes_path.exists()
    assert edges_path.exists()
    assert len(nodes_path.read_text(encoding="utf-8").splitlines()) == snapshot.overview.node_count
    assert len(edges_path.read_text(encoding="utf-8").splitlines()) == snapshot.overview.edge_count
