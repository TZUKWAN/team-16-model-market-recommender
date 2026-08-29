import React from 'react';
import type { EvaluationResponse } from '../types';

interface EvaluationDashboardProps {
  data: EvaluationResponse;
  loading: boolean;
  onRefresh: () => void;
}

const EvaluationDashboard: React.FC<EvaluationDashboardProps> = ({
  data,
  loading,
  onRefresh,
}) => {
  if (!data || data.metrics?.length === 0) return null;

  return (
    <div className="card evaluation-dashboard">
      <div className="dashboard-header">
        <h3 className="card-title">评估指标看板</h3>
        <div className="dashboard-header-actions">
          {data.is_mock && (
            <span className="mock-badge">Mock 数据</span>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={onRefresh}
            disabled={loading}
          >
            {loading ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      <div className="metrics-grid">
        {data.metrics.map((metric) => (
          <div
            key={metric.name}
            className={`metric-card ${metric.is_met ? 'met' : 'not-met'}`}
          >
            <div className="metric-header">
              <span className="metric-name">{metric.name}</span>
              <span className={`metric-status ${metric.is_met ? 'met' : 'not-met'}`}>
                {metric.is_met ? '✓ 达标' : '✗ 未达标'}
              </span>
            </div>
            <div className="metric-values">
              <div className="metric-current">
                <span className="metric-value">{metric.value}</span>
                <span className="metric-unit">{metric.unit}</span>
              </div>
              <div className="metric-target">
                目标：{metric.target}{metric.unit}
              </div>
            </div>
            <div className="metric-bar">
              <div
                className={`metric-bar-fill ${metric.is_met ? 'met' : 'not-met'}`}
                style={{
                  width: `${Math.min(100, (metric.value / metric.target) * 100)}%`,
                }}
              />
            </div>
            {metric.sample_count !== undefined && (
              <div className="metric-samples">
                样本量：{metric.sample_count}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="dashboard-footer">
        <div className="report-time">
          报告时间：{new Date(data.report_generated_at).toLocaleString('zh-CN')}
        </div>
      </div>
    </div>
  );
};

export default EvaluationDashboard;
