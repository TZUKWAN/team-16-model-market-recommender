import type { EvaluationResponse } from '../types';

export function evaluationMock(): EvaluationResponse {
  return {
    metrics: [
      { name: '意图识别准确率', value: 94.2, target: 93, unit: '%', is_met: true, sample_count: 120 },
      { name: '需求→模型标签转换准确率', value: 91.5, target: 90, unit: '%', is_met: true, sample_count: 120 },
      { name: 'Top3 命中率', value: 86.7, target: 85, unit: '%', is_met: true, sample_count: 120 },
      { name: 'Top5 命中率', value: 93.3, target: 92, unit: '%', is_met: true, sample_count: 120 },
      { name: '组合适配度', value: 82.4, target: 80, unit: '%', is_met: true, sample_count: 35 },
    ],
    overall_score: 88.5,
    report_generated_at: new Date().toISOString(),
    is_mock: true,
  };
}
