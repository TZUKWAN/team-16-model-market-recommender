import type { ParseDemandResponse } from './demand';

/** 模型推荐响应 */
export interface RecommendModelsRequest {
  parse_result: ParseDemandResponse;
  model_source?: 'official' | 'demo' | 'official_then_demo';
  top_k?: number;
  demo_top_k?: number;
  prefer_api_available?: boolean;
  prefer_landing_cases?: boolean;
  client_request_id?: string;
}

export interface RecommendModelsResponse {
  request_id: string;
  recommendations: ModelRecommendation[];
  demo_references: ModelRecommendation[];
  unrecommended_examples: UnrecommendedExample[];
  summary: string;
  catalog_policy: 'official' | 'demo' | 'official_then_demo';
  demo_reference_status: 'not_requested' | 'available' | 'unavailable';
  official_recommendation_count: number;
  demo_reference_count: number;
  version_id?: string;
  version_number?: number;
}

export interface ScoreBreakdown {
  scenario_match: number;
  customer_match: number;
  data_match: number;
  output_match: number;
  graph_path_match?: number;
  field_compatibility?: number;
  hybrid_retrieval_match?: number;
  llm_semantic_match?: number;
  performance: number;
  landing_experience: number;
  compliance: number;
}

export interface EvidenceCard {
  evidence_type: string;
  content?: string;
  source?: string;
  evidence_text?: string;
  source_field?: string;
  confidence?: number;
}

export interface AlternativeModel {
  model_id: string;
  model_name: string;
  reason?: string;
  alternative_reason: string;
  weakness_dimensions: string[];
}

export interface DataReadinessReport {
  readiness_score: number;
  required_fields: string[];
  available_fields: string[];
  missing_required_fields: string[];
  missing_optional_fields: string[];
  confidence_impact: string;
  action_items: string[];
  substitution_notes: string[];
}

export interface ModelRecommendation {
  model_id: string;
  model_name: string;
  source?: 'official' | 'demo' | string;
  catalog_version?: string;
  rank: number;
  total_score: number;
  rule_score?: number;
  graph_score?: number;
  retrieval_score?: number;
  llm_score?: number;
  score_breakdown: ScoreBreakdown;
  recommendation_reason: string;
  evidence_cards: EvidenceCard[];
  required_data: string[];
  missing_data: string[];
  output_fields: string[];
  applicable_boundary: string;
  unsuitable_conditions: string;
  compliance_notes: string;
  alternative_models: AlternativeModel[];
  data_readiness?: DataReadinessReport;
}

export interface UnrecommendedExample {
  model_id: string;
  model_name: string;
  reason: string;
}

export interface EffectEstimate {
  estimated_lift_pct: number;
  coverage_pct: number;
  confidence_band_pct: number[];
  data_readiness_factor: number;
  segment_match_factor: number;
  basis: string[];
  disclaimer: string;
  metric_source?: 'verified' | 'draft' | 'missing';
  verification_status?: string;
  evidence_level?: 'high' | 'medium' | 'low';
  assumptions?: string[];
  not_for_decision?: boolean;
}

export interface ModelComparisonItem {
  model_id: string;
  model_name: string;
  domain: string;
  customer_segment: string[];
  input_fields_required: string[];
  output_fields: string[];
  performance_metrics: Record<string, unknown>;
  applicable_conditions: string;
  unsuitable_conditions: string;
  compliance_boundary: string;
  data_readiness: DataReadinessReport;
  effect_estimate: EffectEstimate;
}

export interface CompareModelsRequest {
  model_ids: string[];
  parse_result?: ParseDemandResponse | Record<string, unknown>;
}

export interface CompareModelsResponse {
  request_id: string;
  items: ModelComparisonItem[];
  matrix: Array<{
    dimension: string;
    values: Record<string, string>;
  }>;
  disclaimer: string;
}

export type FeedbackAction = 'adopt' | 'reject' | 'favorite';

export interface FeedbackRequest {
  request_id: string;
  model_id: string;
  model_name?: string;
  action: FeedbackAction;
  reason?: string;
  scenario?: string;
  parse_result?: ParseDemandResponse | Record<string, unknown>;
  metadata?: Record<string, unknown>;
  evidence_mode?: 'human' | 'demo' | 'test';
}

export interface FeedbackResponse {
  event_id: string;
  status: string;
}

export interface ModelFeedbackStats {
  model_id: string;
  model_name: string;
  scenario: string;
  recommended_count: number;
  adopt_count: number;
  reject_count: number;
  favorite_count: number;
  adoption_rate: number;
}

export interface FeedbackStatsResponse {
  total_events: number;
  items: ModelFeedbackStats[];
  human_event_count: number;
  demo_event_count: number;
  test_event_count: number;
}

export interface RecommendationVersionModel {
  model_id: string;
  model_name: string;
  rank: number;
  total_score: number;
}

export interface RecommendationVersionRecord {
  version_id: string;
  version_number: number;
  session_id: string;
  request_id: string;
  created_at: string;
  parse_summary: {
    intent?: string;
    business_scenario?: string;
    business_stage?: string;
    confidence?: number;
  };
  model_ranking: RecommendationVersionModel[];
  config_hash: string;
}

export interface RecommendationVersionListResponse {
  session_id: string;
  versions: RecommendationVersionRecord[];
  count: number;
}

export interface RecommendationVersionRankChange {
  model_id: string;
  model_name: string;
  rank_a: number;
  rank_b: number;
  rank_delta: number;
  score_a: number;
  score_b: number;
  score_delta: number;
}

export interface RecommendationVersionDiffResponse {
  session_id: string;
  version_a: string;
  version_b: string;
  added_models: string[];
  removed_models: string[];
  rank_changes: RecommendationVersionRankChange[];
  summary: string;
}
