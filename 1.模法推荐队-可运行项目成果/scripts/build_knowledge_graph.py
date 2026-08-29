"""Build lightweight knowledge graph JSONL files from model-market assets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.knowledge_graph import KnowledgeGraphService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build model-market knowledge graph JSONL files.")
    parser.add_argument(
        "--nodes",
        default=str(ROOT / "data" / "knowledge" / "graph_nodes.jsonl"),
        help="Output JSONL path for graph nodes.",
    )
    parser.add_argument(
        "--edges",
        default=str(ROOT / "data" / "knowledge" / "graph_edges.jsonl"),
        help="Output JSONL path for graph edges.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service = KnowledgeGraphService()
    snapshot = service.export_jsonl(Path(args.nodes), Path(args.edges))
    overview = snapshot.overview

    print(f"nodes={overview.node_count}")
    print(f"edges={overview.edge_count}")
    print(f"models={overview.model_count}")
    print(f"official_models={overview.official_model_count}")
    print(f"demo_models={overview.demo_model_count}")
    print(f"isolated_nodes={overview.isolated_node_count}")
    print(f"node_types={overview.node_type_counts}")
    print(f"relation_types={overview.relation_type_counts}")

    required_model_nodes = {"model:MKT_001", "model:RISK_001", "model:OFFICIAL_001"}
    node_ids = {node.node_id for node in snapshot.nodes}
    missing = sorted(required_model_nodes - node_ids)
    if missing:
        print(f"missing_required_nodes={missing}", file=sys.stderr)
        return 2
    if overview.node_count <= 0 or overview.edge_count <= 0:
        print("knowledge graph is empty", file=sys.stderr)
        return 3
    if overview.official_model_count < 60 or overview.demo_model_count < 105:
        print("knowledge graph does not cover expected official/demo model counts", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
