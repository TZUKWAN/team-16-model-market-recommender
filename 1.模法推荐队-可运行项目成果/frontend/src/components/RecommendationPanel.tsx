import React, { useState } from 'react';
import type { FeedbackAction, ModelRecommendation } from '../types';

interface RecommendationPanelProps {
  recommendations: ModelRecommendation[];
  selectedModelId: string | null;
  onSelectModel: (recommendation: ModelRecommendation) => void;
  onViewGraph?: (recommendation: ModelRecommendation) => void;
  compareModelIds?: string[];
  onToggleCompare?: (recommendation: ModelRecommendation) => void;
  onFeedback?: (recommendation: ModelRecommendation, action: FeedbackAction, reason: string) => void;
  title?: string;
  description?: string;
  variant?: 'official' | 'demo';
}

const RecommendationPanel: React.FC<RecommendationPanelProps> = ({
  recommendations,
  selectedModelId,
  onSelectModel,
  onViewGraph,
  compareModelIds = [],
  onToggleCompare,
  onFeedback,
  title,
  description,
  variant = 'official',
}) => {
  const [feedbackReasons, setFeedbackReasons] = useState<Record<string, string>>({});

  if (!recommendations || recommendations.length === 0) return null;

  const reasonFor = (modelId: string) => feedbackReasons[modelId] || '';

  return (
    <div className={`card recommendation-panel recommendation-panel-${variant}`}>
      <div className="recommendation-heading">
        <h3 className="card-title">{title || `推荐模型 Top${recommendations.length}`}</h3>
        <span className={`catalog-policy-badge catalog-policy-badge-${variant}`}>
          {variant === 'official' ? '官方目录' : 'Demo 参考'}
        </span>
      </div>
      {description && <p className="recommendation-description">{description}</p>}
      <div className="recommendation-list">
        {recommendations.map((rec) => {
          const inCompare = compareModelIds.includes(rec.model_id);
          return (
            <div
              key={rec.model_id}
              className={`recommendation-card ${selectedModelId === rec.model_id ? 'selected' : ''}`}
              onClick={() => onSelectModel(rec)}
            >
              <div className="rec-header">
                <span className="rec-rank">#{rec.rank}</span>
                <div className="rec-info">
                  <span className="rec-name-row">
                    <span className="rec-name">{rec.model_name}</span>
                    <span className={`rec-source-badge rec-source-badge-${variant}`}>
                      {variant === 'official' ? '官方' : 'Demo'}
                    </span>
                  </span>
                  <span className="rec-id">{rec.model_id}</span>
                </div>
              </div>
              <p className="rec-reason">{rec.recommendation_reason}</p>
              <div className="rec-footer">
                <span className="rec-output-label">主要输出：</span>
                <span className="rec-outputs">{rec.output_fields.join('、')}</span>
              </div>
              <div className="rec-actions" onClick={(event) => event.stopPropagation()}>
                {onToggleCompare && (
                  <button
                    type="button"
                    className={`btn btn-sm ${inCompare ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => onToggleCompare(rec)}
                  >
                    {inCompare ? '移出对比' : '加入对比'}
                  </button>
                )}
                {onViewGraph && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm rec-graph-button"
                    onClick={() => onViewGraph(rec)}
                  >
                    查看图谱
                  </button>
                )}
                {onFeedback && (
                  <>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => onFeedback(rec, 'adopt', reasonFor(rec.model_id))}>采纳</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => onFeedback(rec, 'reject', reasonFor(rec.model_id))}>不采纳</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => onFeedback(rec, 'favorite', reasonFor(rec.model_id))}>收藏</button>
                    <input
                      className="feedback-reason-input"
                      value={reasonFor(rec.model_id)}
                      placeholder="反馈原因"
                      aria-label={`${rec.model_name}反馈原因`}
                      onChange={(event) => setFeedbackReasons((prev) => ({ ...prev, [rec.model_id]: event.target.value }))}
                    />
                  </>
                )}
              </div>
              {rec.missing_data.length > 0 && (
                <div className="rec-missing">
                  <span className="missing-label">数据缺口：</span>
                  <span className="missing-items">{rec.missing_data.join('、')}</span>
                </div>
              )}
              {rec.applicable_boundary && (
                <div className="rec-boundary">
                  <span className="boundary-label">适用边界：</span>
                  <span className="boundary-text">{rec.applicable_boundary}</span>
                </div>
              )}
              {rec.unsuitable_conditions && (
                <div className="rec-unsuitable">
                  <span className="unsuitable-label">慎用场景：</span>
                  <span className="unsuitable-text">{rec.unsuitable_conditions}</span>
                </div>
              )}
              {rec.compliance_notes && (
                <div className="rec-compliance">
                  <span className="compliance-label">合规提示：</span>
                  <span className="compliance-text">{rec.compliance_notes}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default RecommendationPanel;
