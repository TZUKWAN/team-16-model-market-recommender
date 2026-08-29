/** 模型资产详情 */
export interface ModelMetadata {
  model_id: string;
  model_name: string;
  domain: string;
  business_scenario: string[];
  business_stage: string[];
  customer_segment: string[];
  model_capability: string[];
  input_fields_required: string[];
  input_fields_optional: string[];
  output_fields: string[];
  performance_metrics: Record<string, unknown>;
  field_provenance?: Record<string, {
    source_type: string;
    provenance: string;
    verification: string;
  }>;
  applicable_conditions: string;
  unsuitable_conditions: string;
  compliance_boundary: string;
  deployment_status: string;
  api_available: boolean;
  historical_cases: string[];
  tags: string[];
  description: string;
  canonical_name?: string;
  aliases?: string[];
  source?: string;
  asset_version?: string;
  asset_status?: string;
  permission_scope?: string;
  legal_boundary?: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  result_schema?: Record<string, unknown>;
  total_questions?: number;
}
