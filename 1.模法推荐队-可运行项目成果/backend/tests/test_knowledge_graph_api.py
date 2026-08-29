"""API tests for knowledge graph endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_graph_overview_endpoint():
    response = client.get("/api/v1/graph/overview")

    assert response.status_code == 200
    data = response.json()
    assert data["node_count"] >= 700
    assert data["edge_count"] >= 4306
    assert data["model_count"] >= 165
    assert data["official_model_count"] >= 60
    assert data["demo_model_count"] >= 105
    assert data["isolated_node_count"] == 0


def test_graph_model_endpoint_returns_context():
    response = client.get("/api/v1/graph/model/MKT_001")

    assert response.status_code == 200
    data = response.json()
    assert data["center_node_id"] == "model:MKT_001"
    assert any(node["node_id"] == "model:MKT_001" for node in data["nodes"])
    assert any(edge["relation_type"] == "applies_to" for edge in data["edges"])
    assert any(edge["relation_type"] == "outputs" for edge in data["edges"])


def test_graph_scenario_endpoint_accepts_raw_scenario_name():
    response = client.get("/api/v1/graph/scenario/县域新客首贷营销")

    assert response.status_code == 200
    data = response.json()
    assert data["center_node_id"] == "scenario:县域新客首贷营销"
    assert any(node["node_id"] == "model:MKT_001" for node in data["nodes"])
    assert any(edge["relation_type"] == "applies_to" for edge in data["edges"])


def test_graph_match_path_with_model_returns_evidence_edges():
    response = client.post(
        "/api/v1/graph/match-path",
        json={
            "model_id": "MKT_001",
            "max_edges": 30,
            "parse_result": {
                "business_scenario": "县域新客首贷营销",
                "business_stage": "pre_marketing",
                "customer_segment": ["new_customer", "rural_area"],
                "expected_outputs": ["conversion_probability", "ranked_list"],
                "tags": ["customer_marketing", "conversion_prediction", "first_loan"],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model_id"] == "MKT_001"
    assert "scenario:县域新客首贷营销" in data["matched_node_ids"]
    assert "output:conversion_probability" in data["matched_node_ids"]
    assert any(edge["source"] == "model:MKT_001" for edge in data["edges"])
    assert len(data["edges"]) <= 30


def test_graph_model_endpoint_returns_404_for_unknown_model():
    response = client.get("/api/v1/graph/model/NO_SUCH_MODEL")

    assert response.status_code == 404


def test_graph_node_endpoint_returns_neighborhood_for_any_node_type():
    """The generic node endpoint powers graph drilldown for non-model nodes."""
    # First fetch a model to find a connected tag node.
    model_resp = client.get("/api/v1/graph/model/MKT_001")
    assert model_resp.status_code == 200
    tag_node_id = next(
        (n["node_id"] for n in model_resp.json()["nodes"] if n["node_type"] == "tag"),
        None,
    )
    assert tag_node_id is not None

    # Drill into the tag node.
    response = client.get(f"/api/v1/graph/node/{tag_node_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["center_node_id"] == tag_node_id
    assert any(n["node_id"] == tag_node_id for n in data["nodes"])
    # A tag should connect to at least one model.
    assert any(n["node_type"] == "model" for n in data["nodes"])


def test_graph_node_endpoint_returns_404_for_unknown_node():
    response = client.get("/api/v1/graph/node/tag:NO_SUCH_TAG")

    assert response.status_code == 404


def test_graph_match_path_returns_matched_node_ids_for_highlight():
    """match-path must return matched_node_ids usable for frontend path highlight."""
    response = client.post(
        "/api/v1/graph/match-path",
        json={
            "model_id": "MKT_001",
            "max_edges": 40,
            "parse_result": {
                "business_scenario": "县域新客首贷营销",
                "business_stage": "pre_marketing",
                "customer_segment": ["new_customer"],
                "expected_outputs": ["conversion_probability"],
                "tags": ["customer_marketing", "conversion_prediction"],
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["model_id"] == "MKT_001"
    assert len(data["matched_node_ids"]) > 0
    assert "model:MKT_001" in data["matched_node_ids"]
    # Every node in matched_node_ids must exist in the returned nodes list.
    returned_ids = {n["node_id"] for n in data["nodes"]}
    for mid in data["matched_node_ids"]:
        assert mid in returned_ids
    # Summary must be non-empty for evidence.
    assert len(data["summary"]) > 0


def test_graph_match_path_404_for_unknown_model():
    response = client.post(
        "/api/v1/graph/match-path",
        json={"model_id": "NO_SUCH_MODEL", "parse_result": {}},
    )

    assert response.status_code == 404
