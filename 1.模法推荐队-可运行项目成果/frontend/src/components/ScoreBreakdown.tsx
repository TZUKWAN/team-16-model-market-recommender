import React from 'react';
import type { ScoreBreakdown as ScoreBreakdownType } from '../types';

interface ScoreBreakdownProps {
  scores: ScoreBreakdownType;
  modelName: string;
}

const DIMENSION_LABELS: Record<keyof ScoreBreakdownType, string> = {
  scenario_match: '场景匹配',
  customer_match: '客群匹配',
  data_match: '数据匹配',
  output_match: '输出匹配',
  graph_path_match: '图谱路径',
  field_compatibility: '字段兼容',
  hybrid_retrieval_match: '混合检索',
  llm_semantic_match: 'LLM语义',
  performance: '性能表现',
  landing_experience: '落地经验',
  compliance: '合规性',
};

const ScoreBreakdown: React.FC<ScoreBreakdownProps> = ({ scores, modelName }) => {
  const entries = (Object.entries(scores)
    .filter(([, value]) => typeof value === 'number')
    .filter(([, value]) => Number.isFinite(value))
  ) as [keyof ScoreBreakdownType, number][];

  return (
    <div className="card score-breakdown">
      <h3 className="card-title">评分拆解：{modelName}</h3>
      <div className="score-bars">
        {entries.map(([key, value]) => (
          <div key={key} className="score-bar-item">
            <div className="score-bar-header">
              <span className="score-dimension">{DIMENSION_LABELS[key] ?? key}</span>
              <span className="score-value">{value}</span>
            </div>
            <div className="score-bar-track">
              <div
                className={`score-bar-fill ${value >= 90 ? 'excellent' : value >= 80 ? 'good' : value >= 70 ? 'fair' : 'poor'}`}
                style={{ width: `${value}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ScoreBreakdown;
