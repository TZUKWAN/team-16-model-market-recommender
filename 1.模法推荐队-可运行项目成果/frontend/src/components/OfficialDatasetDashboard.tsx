import React, { useState, useEffect, useCallback } from 'react';
import type {
  OfficialEvalSummary,
  OfficialDatasetInfo,
  OfficialEvalResults,
  OfficialEvalFailure,
} from '../types';
import {
  fetchOfficialEvaluationResults,
  fetchOfficialEvaluationFailures,
} from '../api/client';
import LoadingState from './LoadingState';
import ErrorState from './ErrorState';
import EmptyState from './EmptyState';

interface OfficialDatasetDashboardProps {
  summary: OfficialEvalSummary;
  dataset: OfficialDatasetInfo;
}

const FAILURE_TYPES = ['all', 'confused_model', 'business_scenario_mismatch', 'unknown'] as const;

const FAILURE_TYPE_LABELS: Record<string, string> = {
  all: '全部类型',
  confused_model: '模型混淆',
  business_scenario_mismatch: '场景不匹配',
  unknown: '未知原因',
};

function pctStr(rate: number): string {
  return rate.toFixed(1) + '%';
}

function hitInfo(hits: number, total: number, rate: number): string {
  return `${pctStr(rate)}（${hits}/${total}）`;
}

/** 将 recommended_top5 中的 model_id 映射为 model_name，找不到则回退显示 id */
function resolveModelName(
  modelId: string,
  models: readonly { model_id: string; model_name: string }[]
): string {
  const found = models.find((m) => m.model_id === modelId);
  return found ? found.model_name : modelId;
}

const OfficialDatasetDashboard: React.FC<OfficialDatasetDashboardProps> = ({
  summary,
  dataset,
}) => {
  // Results split toggle
  const [activeSplit, setActiveSplit] = useState<'val' | 'test'>('val');

  // Failures filters (independent from results)
  const [failureSplit, setFailureSplit] = useState<'all' | 'val' | 'test'>('all');
  const [selectedFailureType, setSelectedFailureType] = useState<string>('all');

  // Results state
  const [resultsData, setResultsData] = useState<OfficialEvalResults | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);

  // Failures state
  const [failuresData, setFailuresData] = useState<OfficialEvalFailure[]>([]);
  const [failuresLoading, setFailuresLoading] = useState(false);
  const [failuresError, setFailuresError] = useState<string | null>(null);

  const loadResults = useCallback(async (split: 'val' | 'test') => {
    setResultsLoading(true);
    setResultsError(null);
    try {
      const data = await fetchOfficialEvaluationResults(split);
      setResultsData(data);
    } catch (err: any) {
      setResultsError(err.message || '加载推荐结果失败');
    }
    setResultsLoading(false);
  }, []);

  const loadFailures = useCallback(
    async (fSplit: 'all' | 'val' | 'test', fType: string) => {
      setFailuresLoading(true);
      setFailuresError(null);
      try {
        const s = fSplit === 'all' ? undefined : fSplit;
        const ft = fType === 'all' ? undefined : fType;
        const data = await fetchOfficialEvaluationFailures(
          s as 'val' | 'test' | undefined,
          ft
        );
        setFailuresData(data);
      } catch (err: any) {
        setFailuresError(err.message || '加载错误样本失败');
      }
      setFailuresLoading(false);
    },
    []
  );

  // Load results when activeSplit changes
  useEffect(() => {
    loadResults(activeSplit);
  }, [activeSplit, loadResults]);

  // Load failures when failureSplit or selectedFailureType changes
  useEffect(() => {
    loadFailures(failureSplit, selectedFailureType);
  }, [failureSplit, selectedFailureType, loadFailures]);

  return (
    <div className="official-dashboard">
      {/* ===== 1. Dataset Overview ===== */}
      <div className="card">
        <h3 className="card-title">数据集概览</h3>
        <div className="official-overview-grid">
          <div className="official-overview-item">
            <span className="official-overview-label">官方模型数</span>
            <span className="official-overview-value">{dataset.model_count}</span>
          </div>
          <div className="official-overview-item">
            <span className="official-overview-label">Query 总数</span>
            <span className="official-overview-value">{dataset.query_count}</span>
          </div>
          <div className="official-overview-item">
            <span className="official-overview-label">训练集</span>
            <span className="official-overview-value">{dataset.splits.train}</span>
          </div>
          <div className="official-overview-item">
            <span className="official-overview-label">测试集</span>
            <span className="official-overview-value">{dataset.splits.test}</span>
          </div>
          <div className="official-overview-item">
            <span className="official-overview-label">验证集</span>
            <span className="official-overview-value">{dataset.splits.val}</span>
          </div>
          <div className="official-overview-item">
            <span className="official-overview-label">数据来源</span>
            <span className="official-overview-value source">{dataset.manifest.source}</span>
          </div>
        </div>
      </div>

      {/* ===== 2. Metric Cards ===== */}
      <div className="card">
        <h3 className="card-title">评估指标</h3>
        <div className="official-metrics-grid">
          <div className="official-metric-card">
            <span className="official-metric-name">Val Top1</span>
            <span className="official-metric-value">{pctStr(summary.val.top1_rate)}</span>
            <span className="official-metric-detail">{hitInfo(summary.val.top1_hits, summary.val.total, summary.val.top1_rate)}</span>
          </div>
          <div className="official-metric-card">
            <span className="official-metric-name">Val Top3</span>
            <span className="official-metric-value">{pctStr(summary.val.top3_rate)}</span>
            <span className="official-metric-detail">{hitInfo(summary.val.top3_hits, summary.val.total, summary.val.top3_rate)}</span>
          </div>
          <div className="official-metric-card">
            <span className="official-metric-name">Val Top5</span>
            <span className="official-metric-value">{pctStr(summary.val.top5_rate)}</span>
            <span className="official-metric-detail">{hitInfo(summary.val.top5_hits, summary.val.total, summary.val.top5_rate)}</span>
          </div>
          <div className="official-metric-card">
            <span className="official-metric-name">Test Top1</span>
            <span className="official-metric-value">{pctStr(summary.test.top1_rate)}</span>
            <span className="official-metric-detail">{hitInfo(summary.test.top1_hits, summary.test.total, summary.test.top1_rate)}</span>
          </div>
          <div className="official-metric-card">
            <span className="official-metric-name">Test Top3</span>
            <span className="official-metric-value">{pctStr(summary.test.top3_rate)}</span>
            <span className="official-metric-detail">{hitInfo(summary.test.top3_hits, summary.test.total, summary.test.top3_rate)}</span>
          </div>
          <div className="official-metric-card">
            <span className="official-metric-name">Test Top5</span>
            <span className="official-metric-value">{pctStr(summary.test.top5_rate)}</span>
            <span className="official-metric-detail">{hitInfo(summary.test.top5_hits, summary.test.total, summary.test.top5_rate)}</span>
          </div>
        </div>
      </div>

      {/* ===== 3. Results Table ===== */}
      <div className="card">
        <h3 className="card-title">推荐结果明细</h3>
        {resultsLoading && <LoadingState message="加载推荐结果..." />}
        {resultsError && (
          <ErrorState message={resultsError} onRetry={() => loadResults(activeSplit)} />
        )}
        {resultsData && !resultsLoading && (
          <div className="official-table-wrapper">
            <table className="official-table">
              <thead>
                <tr>
                  <th>Split</th>
                  <th>Query</th>
                  <th>目标模型</th>
                  <th>推荐 Top5</th>
                  <th>Top1</th>
                  <th>Top3</th>
                  <th>Top5</th>
                </tr>
              </thead>
              <tbody>
                {resultsData.results.length === 0 ? (
                  <tr>
                    <td colSpan={7}>
                      <EmptyState message="暂无推荐结果数据" />
                    </td>
                  </tr>
                ) : (
                  resultsData.results.map((item) => (
                    <tr key={item.query_id}>
                      <td>
                        <span className={`official-split-badge ${item.split}`}>
                          {item.split}
                        </span>
                      </td>
                      <td className="official-query-cell" title={item.query}>
                        {item.query.length > 24
                          ? item.query.slice(0, 24) + '…'
                          : item.query}
                      </td>
                      <td className="official-gold-cell">
                        {item.gold_model_names.join(', ')}
                      </td>
                      <td className="official-top5-cell">
                        {item.recommended_top5.map((id, i) => (
                          <span key={i} className="official-rec-tag">
                            {resolveModelName(id, item.recommended_models)}
                          </span>
                        ))}
                      </td>
                      <td>
                        <span className={item.top1_hit ? 'hit-badge' : 'miss-badge'}>
                          {item.top1_hit ? '✓' : '✗'}
                        </span>
                      </td>
                      <td>
                        <span className={item.top3_hit ? 'hit-badge' : 'miss-badge'}>
                          {item.top3_hit ? '✓' : '✗'}
                        </span>
                      </td>
                      <td>
                        <span className={item.top5_hit ? 'hit-badge' : 'miss-badge'}>
                          {item.top5_hit ? '✓' : '✗'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ===== 4. Failure Samples ===== */}
      <div className="card">
        <h3 className="card-title">错误样本分析</h3>

        <div className="official-filters">
          <div className="official-filter-group">
            <span className="official-filter-label">Split：</span>
            <div className="official-filter-btns">
              {(['all', 'val', 'test'] as const).map((v) => (
                <button
                  key={v}
                  className={`official-filter-btn ${failureSplit === v ? 'active' : ''}`}
                  onClick={() => setFailureSplit(v)}
                >
                  {v === 'all' ? '全部' : v === 'val' ? '验证集' : '测试集'}
                </button>
              ))}
            </div>
          </div>

          <div className="official-filter-group">
            <span className="official-filter-label">错误类型：</span>
            <div className="official-filter-btns">
              {FAILURE_TYPES.map((ft) => (
                <button
                  key={ft}
                  className={`official-filter-btn ${selectedFailureType === ft ? 'active' : ''}`}
                  onClick={() => setSelectedFailureType(ft)}
                >
                  {FAILURE_TYPE_LABELS[ft]}
                </button>
              ))}
            </div>
          </div>
        </div>

        {failuresLoading && <LoadingState message="加载错误样本..." />}
        {failuresError && (
          <ErrorState message={failuresError} onRetry={() => loadFailures(failureSplit, selectedFailureType)} />
        )}

        {!failuresLoading && !failuresError && failuresData.length === 0 && (
          <EmptyState
            message="当前筛选条件下无错误样本"
            hint="尝试切换 Split 或错误类型"
          />
        )}

        {!failuresLoading && !failuresError && failuresData.length > 0 && (
          <div className="official-failure-list">
            {failuresData.map((failure) => (
              <div key={failure.query_id} className="official-failure-card">
                <div className="official-failure-header">
                  <span className="official-failure-id">{failure.query_id}</span>
                  <span className={`official-split-badge ${failure.split}`}>
                    {failure.split}
                  </span>
                  <span className={`official-scope-badge ${failure.failure_scope}`}>
                    {failure.failure_scope === 'top1_miss'
                      ? 'Top1 未命中'
                      : failure.failure_scope === 'top3_miss'
                      ? 'Top3 未命中'
                      : 'Top5 未命中'}
                  </span>
                  <span className="official-failure-type-tag">
                    {FAILURE_TYPE_LABELS[failure.failure_type] || failure.failure_type}
                  </span>
                </div>
                <div className="official-failure-body">
                  <div className="official-failure-field">
                    <span className="official-failure-field-label">Query：</span>
                    <span>{failure.query}</span>
                  </div>
                  <div className="official-failure-field">
                    <span className="official-failure-field-label">目标模型：</span>
                    <span>{failure.gold_model_names.join('、')}</span>
                  </div>
                  <div className="official-failure-field">
                    <span className="official-failure-field-label">推荐 Top5：</span>
                    <span>
                      {failure.recommended_top5
                        .map((id) => resolveModelName(id, failure.recommended_models))
                        .join(' → ')}
                    </span>
                  </div>
                  <div className="official-failure-reason">
                    <span className="official-failure-field-label">原因分析：</span>
                    <p>{failure.reason}</p>
                  </div>
                  <div className="official-failure-fix">
                    <span className="official-failure-field-label">修复建议：</span>
                    <p>{failure.suggested_fix}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default OfficialDatasetDashboard;
