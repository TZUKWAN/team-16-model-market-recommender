import React, { useMemo } from 'react';
import type { ModelRecommendation } from '../types';

interface Props {
  firstRound: ModelRecommendation[];
  finalRound: ModelRecommendation[];
}

interface ChangedItem {
  model: ModelRecommendation;
  oldRank: number;
}

const RecommendationDiff: React.FC<Props> = ({ firstRound, finalRound }) => {
  const diff = useMemo(() => {
    const firstMap = new Map(firstRound.map((r) => [r.model_id, r]));
    const finalMap = new Map(finalRound.map((r) => [r.model_id, r]));
    const allIds = new Set([...firstMap.keys(), ...finalMap.keys()]);
    const added: ModelRecommendation[] = [];
    const removed: ModelRecommendation[] = [];
    const changed: ChangedItem[] = [];

    for (const id of allIds) {
      const f = firstMap.get(id);
      const l = finalMap.get(id);
      if (!f && l) {
        added.push(l);
      } else if (f && !l) {
        removed.push(f);
      } else if (f && l) {
        if (f.rank !== l.rank) {
          changed.push({ model: l, oldRank: f.rank });
        }
      }
    }
    return { added, removed, changed };
  }, [firstRound, finalRound]);

  if (firstRound.length === 0 || finalRound.length === 0) {
    return null;
  }

  const hasDiff =
    diff.added.length > 0 || diff.removed.length > 0 || diff.changed.length > 0;

  return (
    <div className="card recommendation-diff">
      <h3 className="card-title">推荐版本对比</h3>
      <p className="panel-hint">
        展示多轮澄清前后推荐结果的变化，直观体现澄清价值。
      </p>
      {!hasDiff ? (
        <div className="diff-no-change">多轮澄清后推荐结果无变化。</div>
      ) : (
        <div className="diff-content">
          {diff.added.length > 0 && (
            <div className="diff-section diff-added">
              <div className="diff-section-title">新增推荐（{diff.added.length}）</div>
              {diff.added.map((m) => (
                <div key={m.model_id} className="diff-row">
                  <span className="diff-model-name">{m.model_name}</span>
                  <span className="diff-badge diff-badge-add">+ 新增</span>
                  <span className="diff-rank-change">排名 {m.rank}</span>
                </div>
              ))}
            </div>
          )}
          {diff.removed.length > 0 && (
            <div className="diff-section diff-removed">
              <div className="diff-section-title">移除推荐（{diff.removed.length}）</div>
              {diff.removed.map((m) => (
                <div key={m.model_id} className="diff-row">
                  <span className="diff-model-name">{m.model_name}</span>
                  <span className="diff-badge diff-badge-remove">- 移除</span>
                  <span className="diff-rank-change">原排名 {m.rank}</span>
                </div>
              ))}
            </div>
          )}
          {diff.changed.length > 0 && (
            <div className="diff-section diff-changed">
              <div className="diff-section-title">排名变化（{diff.changed.length}）</div>
              {diff.changed.map(({ model, oldRank }) => {
                const rankDelta = oldRank - model.rank;
                return (
                  <div key={model.model_id} className="diff-row">
                    <span className="diff-model-name">{model.model_name}</span>
                    <span className="diff-rank-change">
                      排名 {oldRank} → {model.rank}
                      {rankDelta > 0 && <span className="diff-up"> ↑{rankDelta}</span>}
                      {rankDelta < 0 && <span className="diff-down"> ↓{Math.abs(rankDelta)}</span>}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RecommendationDiff;
