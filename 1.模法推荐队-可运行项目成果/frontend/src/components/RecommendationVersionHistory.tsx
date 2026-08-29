import React, { useEffect, useMemo, useState } from 'react';
import { GitCompareArrows, RefreshCw } from 'lucide-react';
import { diffRecommendationVersions } from '../api/client';
import type {
  RecommendationVersionDiffResponse,
  RecommendationVersionRecord,
} from '../types';

interface Props {
  sessionId: string;
  versions: RecommendationVersionRecord[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

const versionLabel = (version: RecommendationVersionRecord) => {
  const scenario = version.parse_summary.business_scenario || version.parse_summary.intent || '未标注场景';
  const created = version.created_at ? new Date(version.created_at).toLocaleString('zh-CN') : '时间未知';
  return `V${version.version_number} · ${scenario} · ${created}`;
};

const RecommendationVersionHistory: React.FC<Props> = ({
  sessionId,
  versions,
  loading,
  error,
  onRefresh,
}) => {
  const ordered = useMemo(
    () => [...versions].sort((a, b) => a.version_number - b.version_number),
    [versions]
  );
  const [versionA, setVersionA] = useState('');
  const [versionB, setVersionB] = useState('');
  const [diff, setDiff] = useState<RecommendationVersionDiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const visibleRankChanges = (diff?.rank_changes || []).filter(
    (change) => change.rank_a !== change.rank_b
  );

  useEffect(() => {
    if (ordered.length < 2) {
      setVersionA('');
      setVersionB('');
      setDiff(null);
      return;
    }
    setVersionA((current) => (
      ordered.some((item) => item.version_id === current) ? current : ordered[0].version_id
    ));
    setVersionB((current) => (
      ordered.some((item) => item.version_id === current)
        ? current
        : ordered[ordered.length - 1].version_id
    ));
    setDiff(null);
  }, [ordered]);

  const compare = async () => {
    if (!sessionId || !versionA || !versionB || versionA === versionB) return;
    setDiffLoading(true);
    setDiffError(null);
    try {
      setDiff(await diffRecommendationVersions(sessionId, versionA, versionB));
    } catch (err: any) {
      setDiff(null);
      setDiffError(err.message || '版本对比失败');
    } finally {
      setDiffLoading(false);
    }
  };

  return (
    <section className="version-history" aria-labelledby="version-history-title">
      <div className="version-history-header">
        <div>
          <h3 id="version-history-title">持久化推荐版本</h3>
          <p>版本保存在服务端，并记录算法配置哈希；刷新页面后仍可追溯。</p>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onRefresh}
          disabled={loading || !sessionId}
          title="刷新推荐版本"
          aria-label="刷新推荐版本"
        >
          <RefreshCw size={18} />
        </button>
      </div>

      {error && <div className="version-history-error">{error}</div>}
      {!error && ordered.length === 0 && (
        <div className="version-history-empty">当前会话尚未产生推荐版本。</div>
      )}
      {ordered.length > 0 && (
        <div className="version-history-list">
          {ordered.map((version) => (
            <div className="version-history-item" key={version.version_id}>
              <span>V{version.version_number}</span>
              <strong>{version.parse_summary.business_scenario || version.parse_summary.intent || '未标注场景'}</strong>
              <span>{version.model_ranking.slice(0, 3).map((item) => item.model_name || item.model_id).join('、')}</span>
            </div>
          ))}
        </div>
      )}

      {ordered.length >= 2 && (
        <div className="version-compare-controls">
          <label>
            基准版本
            <select value={versionA} onChange={(event) => setVersionA(event.target.value)}>
              {ordered.map((version) => (
                <option value={version.version_id} key={version.version_id}>{versionLabel(version)}</option>
              ))}
            </select>
          </label>
          <label>
            对比版本
            <select value={versionB} onChange={(event) => setVersionB(event.target.value)}>
              {ordered.map((version) => (
                <option value={version.version_id} key={version.version_id}>{versionLabel(version)}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={compare}
            disabled={diffLoading || versionA === versionB}
          >
            <GitCompareArrows size={18} />
            {diffLoading ? '对比中' : '对比版本'}
          </button>
        </div>
      )}

      {diffError && <div className="version-history-error">{diffError}</div>}
      {diff && (
        <div className="version-persisted-diff" aria-live="polite">
          <strong>
            新增 {diff.added_models.length} 个模型，移除 {diff.removed_models.length} 个模型，
            {visibleRankChanges.length} 个模型排名变化。
          </strong>
          {diff.added_models.length > 0 && <p>新增：{diff.added_models.join('、')}</p>}
          {diff.removed_models.length > 0 && <p>移除：{diff.removed_models.join('、')}</p>}
          {visibleRankChanges.map((change) => (
            <p key={change.model_id}>
              {change.model_name || change.model_id}：排名 {change.rank_a} → {change.rank_b}
            </p>
          ))}
        </div>
      )}
    </section>
  );
};

export default RecommendationVersionHistory;
