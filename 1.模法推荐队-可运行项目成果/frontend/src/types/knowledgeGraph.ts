export interface GraphNode {
  node_id: string;
  node_type: string;
  name: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  edge_id: string;
  source: string;
  target: string;
  relation_type: string;
  weight: number;
  evidence: Record<string, unknown>;
}

export interface GraphNeighborhood {
  center_node_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphMatchPathResponse {
  model_id: string;
  matched_node_ids: string[];
  nodes: GraphNode[];
  edges: GraphEdge[];
  summary: string;
}
