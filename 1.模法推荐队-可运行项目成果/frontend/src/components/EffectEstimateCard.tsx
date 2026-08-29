import React from 'react';
import type { ModelComparisonItem } from '../types';

interface EffectEstimateCardProps {
  item: ModelComparisonItem;
}

const EVIDENCE_LABELS: Record<string, string> = {
  high: '可核验指标',
  medium: '草案指标',
  low: '保守估计',
};

const EVIDENCE_COLORS: Record<string, string> = {
  high: '#059669',
  medium: '#d97706',
  low: '#dc2626',
};

const SOURCE_LABELS: Record<string, string> = {
  verified: '已验证',
  draft: '草案',
  missing: '无指标',
};

const EffectEstimateCard: React.FC<EffectEstimateCardProps> = ({ item }) => {
  const estimate = item.effect_estimate as any;
  const evidenceLevel = estimate.evidence_level ?? 'low';
  const metricSource = estimate.metric_source ?? 'missing';
  const notForDecision = estimate.not_for_decision ?? true;

  return (
    <div className="effect-card">
      <div className="effect-card-header">
        <span className="effect-model-name">{item.model_name}</span>
        <span className="effect-model-id">{item.model_id}</span>
      </div>

      <div className="effect-evidence-badge" style={{ color: EVIDENCE_COLORS[evidenceLevel] }}>
        <span className="effect-evidence-dot" style={{ background: EVIDENCE_COLORS[evidenceLevel] }} />
        {EVIDENCE_LABELS[evidenceLevel] ?? evidenceLevel}
        <span className="effect-evidence-source">
          （指标来源：{SOURCE_LABELS[metricSource] ?? metricSource}）
        </span>
      </div>
      <div className="effect-verification">{estimate.verification_status ?? '未验证'}</div>

      <div className="effect-metric-row">
        <span>预期提升</span>
        <strong>待验证</strong>
      </div>
      <div className="effect-metric-row">
        <span>覆盖率</span>
        <strong>待验证</strong>
      </div>
      <div className="effect-band">启发式估计，非统计推断</div>

      {estimate.assumptions && estimate.assumptions.length > 0 && (
        <details className="effect-assumptions">
          <summary>预估假设（{estimate.assumptions.length}）</summary>
          <ul>
            {estimate.assumptions.map((a: string, i: number) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </details>
      )}

      <div className="effect-note">
        {estimate.disclaimer}
        {notForDecision && (
          <span className="effect-not-for-decision"> 仅供参考，不可直接用于业务决策。</span>
        )}
      </div>
    </div>
  );
};

export default EffectEstimateCard;
