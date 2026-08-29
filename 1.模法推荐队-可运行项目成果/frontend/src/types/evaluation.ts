/** 评估指标响应 */
export interface EvaluationMetric {
  name: string;
  value: number;
  target: number;
  unit: string;
  is_met: boolean;
  sample_count?: number;
}

export interface EvaluationResponse {
  metrics: EvaluationMetric[];
  overall_score: number;
  report_generated_at: string;
  is_mock: boolean;
  total_models_covered?: number;
  total_samples?: number;
}
