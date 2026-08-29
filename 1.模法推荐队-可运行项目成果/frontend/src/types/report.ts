import type { ParseDemandResponse } from './demand';
import type { RecommendModelsResponse } from './recommendation';
import type { CompositionResponse } from './composition';
import type { ModelInvokeResponse } from './inference';

/** 报告请求 */
export interface ReportRequest {
  request_id?: string;
  format?: 'markdown' | 'html' | 'pdf';
  include_details?: boolean;
  /** 用户原始需求文本 */
  demand_raw: string;
  parse_result?: ParseDemandResponse;
  recommend_result?: RecommendModelsResponse;
  composition_result?: CompositionResponse;
  model_result?: ModelInvokeResponse;
}

export interface ReportSection {
  title: string;
  content: string;
}

export interface ReportTopModel {
  rank: number;
  model_name: string;
  score: number;
  reason: string;
}

export interface ReportSystemUnderstanding {
  intent: string;
  domain: string;
  scenario: string;
  tags: string[];
  translation: string;
}

export interface ReportBestComposition {
  name: string;
  score: number;
  steps: string[];
}

export interface ReportData {
  report_id: string;
  request_id?: string;
  generated_at: string;
  format?: string;
  title?: string;
  summary?: string;
  generation_source?: 'rule' | 'llm' | 'fallback';
  llm_trace_id?: string;
  sections?: ReportSection[];
  raw_content?: string;
  /** 一页纸报告展示字段 */
  user_demand?: string;
  system_understanding?: ReportSystemUnderstanding;
  top3_models?: ReportTopModel[];
  best_composition?: ReportBestComposition;
  required_data?: string[];
  data_gaps?: string[];
  implementation_steps?: string[];
  risk_tips?: string[];
}
