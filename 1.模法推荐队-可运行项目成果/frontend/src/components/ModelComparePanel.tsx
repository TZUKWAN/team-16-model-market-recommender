import React from 'react';
import type { CompareModelsResponse } from '../types';
import EffectEstimateCard from './EffectEstimateCard';

interface ModelComparePanelProps {
  data: CompareModelsResponse | null;
  selectedIds: string[];
  loading?: boolean;
  error?: string | null;
  onRemove: (modelId: string) => void;
  onClear: () => void;
}

const ModelComparePanel: React.FC<ModelComparePanelProps> = ({
  data,
  selectedIds,
  loading = false,
  error = null,
  onRemove,
  onClear,
}) => {
  if (selectedIds.length === 0) return null;

  return (
    <div className="card model-compare-panel">
      <div className="panel-title-row">
        <h3 className="card-title">模型横向对比</h3>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClear}>清空</button>
      </div>

      <div className="compare-chip-row">
        {selectedIds.map((id) => (
          <button key={id} type="button" className="compare-chip" onClick={() => onRemove(id)}>
            {id} ×
          </button>
        ))}
      </div>

      {selectedIds.length < 2 && (
        <div className="compare-placeholder">已选择 {selectedIds.length} 个模型，选择至少 2 个后生成对比。</div>
      )}
      {loading && <div className="compare-placeholder">正在生成对比...</div>}
      {error && <div className="compare-error">{error}</div>}

      {data && data.items.length >= 2 && (
        <>
          <div className="effect-grid">
            {data.items.map((item) => <EffectEstimateCard key={item.model_id} item={item} />)}
          </div>
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th>维度</th>
                  {data.items.map((item) => (
                    <th key={item.model_id}>{item.model_name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.matrix.map((row) => (
                  <tr key={row.dimension}>
                    <td>{row.dimension}</td>
                    {data.items.map((item) => (
                      <td key={item.model_id}>{row.values[item.model_id] || '-'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="compare-disclaimer">{data.disclaimer}</div>
        </>
      )}
    </div>
  );
};

export default ModelComparePanel;