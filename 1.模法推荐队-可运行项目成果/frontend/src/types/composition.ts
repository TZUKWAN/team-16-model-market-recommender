/** 组合推荐响应 */
export interface CompositionNode {
  node_id?: string;
  step_order: number;
  model_id: string;
  model_name: string;
  source?: 'official' | 'demo';
  catalog_version?: string;
  capability: string;
  input_requirements?: string[];
  output_fields: string[];
  fit_score?: number;
  node_explanation?: string;
  step_id?: string;
  input_fields?: string[];
}

export interface FlowEdge {
  source_node_id?: string;
  target_node_id?: string;
  io_status?: string;
  missing_fields?: string[];
  suggestion?: string;
  from_step?: string;
  to_step?: string;
  reason?: string;
}

export interface IOCompatibility {
  total_edges: number;
  passed: number;
  partial: number;
  failed: number;
  compatibility_rate: number;
  [key: string]: any;
}

export interface UsageGuide {
  step: string;
  description: string;
  estimated_time?: string;
  data_preparation?: string;
}

export interface CompositionExecutionNode {
  node_id: string;
  step_order: number;
  model_id: string;
  model_name: string;
  capability: string;
  status: string;
  input_snapshot: Record<string, any>;
  output_snapshot: Record<string, any>;
  started_at: string;
  finished_at: string;
  elapsed_ms: number;
  demo_data: boolean;
  desensitized_notice: string;
  status_reason?: string;
}

export interface CompositionExecutionEdge {
  source_node_id: string;
  target_node_id: string;
  status: string;
  transferred_fields: string[];
  note: string;
}

export interface CompositionExecutionResult {
  execution_id: string;
  status: string;
  demo_data: boolean;
  desensitized_notice: string;
  nodes: CompositionExecutionNode[];
  edges: CompositionExecutionEdge[];
  fused_result: Record<string, any>;
}

export interface CompositionResponse {
  composition_id: string;
  composition_name: string;
  scenario: string;
  total_score: number;
  composition_status?: 'ready' | 'degraded' | 'partially_blocked' | 'blocked' | 'no_template';
  failure_reasons?: string[];
  demo_execution_only?: boolean;
  nodes: CompositionNode[];
  flow_edges: FlowEdge[];
  io_compatibility: IOCompatibility;
  missing_data: string[];
  expected_outputs: string[];
  business_explanation: string;
  technical_explanation: string;
  management_explanation: string;
  usage_guide: Array<UsageGuide | string>;
  execution_result?: CompositionExecutionResult | null;
}
