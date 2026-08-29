import React from 'react';
import type { FeedbackStatsResponse } from '../types';

interface AdoptionStatsProps {
  data: FeedbackStatsResponse | null;
}

const AdoptionStats: React.FC<AdoptionStatsProps> = ({ data }) => {
  if (!data || data.items.length === 0) return null;
  const items = data.items.slice(0, 5);

  return (
    <div className="card adoption-stats">
      <h3 className="card-title">采纳反馈</h3>
      <div className="adoption-list">
        {items.map((item) => (
          <div key={`${item.model_id}-${item.scenario}`} className="adoption-row">
            <div>
              <div className="adoption-name">{item.model_name || item.model_id}</div>
              <div className="adoption-meta">推荐 {item.recommended_count} · 采纳 {item.adopt_count} · 收藏 {item.favorite_count}</div>
            </div>
            <strong>{Math.round(item.adoption_rate * 100)}%</strong>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AdoptionStats;