import React, { useState } from 'react';
import type { AlternativeModel, DataReadinessReport, UnrecommendedExample } from '../types';

interface DataGapPanelProps {
  requiredData: string[];
  missingData: string[];
  alternativeModels: AlternativeModel[];
  dataReadiness?: DataReadinessReport;
  unrecommendedExamples?: UnrecommendedExample[];
}

const DataGapPanel: React.FC<DataGapPanelProps> = ({
  requiredData,
  missingData,
  alternativeModels,
  dataReadiness,
  unrecommendedExamples,
}) => {
  const [showAlternatives, setShowAlternatives] = useState(false);

  return (
    <div className="card data-gap-panel">
      <h3 className="card-title">数据缺口与替代方案</h3>

      {dataReadiness && (
        <div className="readiness-summary">
          <span className="readiness-label">数据就绪分析</span>
          <p>{dataReadiness.confidence_impact}</p>
        </div>
      )}

      <div className="gap-section">
        <span className="label">所需数据</span>
        <div className="data-tags">
          {requiredData.map((d) => (
            <span
              key={d}
              className={`data-tag ${missingData.includes(d) ? 'missing' : 'available'}`}
            >
              {missingData.includes(d) ? '⚠ ' : '✓ '}
              {d}
            </span>
          ))}
        </div>
      </div>

      {missingData.length > 0 ? (
        <div className="gap-section missing-section">
          <span className="label missing-label">数据缺口</span>
          <ul className="missing-list">
            {missingData.map((d) => (
              <li key={d} className="missing-item">
                <span>{d}</span>
                <span className="missing-hint">建议联系数据部门协调获取</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="gap-section satisfied-section">
          <span className="label">数据就绪情况</span>
          <p className="satisfied-text">数据条件基本满足，可直接使用推荐模型。</p>
        </div>
      )}

      {dataReadiness && dataReadiness.action_items.length > 0 && (
        <div className="gap-section">
          <span className="label">补齐动作</span>
          <ul className="missing-list">
            {dataReadiness.action_items.map((item) => (
              <li key={item} className="missing-item">
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {alternativeModels.length > 0 && (
        <div className="gap-section">
          <div className="alternative-header">
            <span className="label">替代模型推荐</span>
            <button
              className="btn btn-text btn-sm"
              onClick={() => setShowAlternatives(!showAlternatives)}
            >
              {showAlternatives ? '收起' : '展开'}
            </button>
          </div>
          {showAlternatives && (
            <div className="alternative-list">
              {alternativeModels.map((alt) => (
                <div key={alt.model_id} className="alternative-item">
                  <div className="alternative-header-row">
                    <span className="alternative-name">{alt.model_name}</span>
                    <span className="alternative-id">{alt.model_id}</span>
                  </div>
                  <p className="alternative-reason">{alt.alternative_reason || alt.reason}</p>
                  {alt.weakness_dimensions && alt.weakness_dimensions.length > 0 && (
                    <div className="alternative-weakness">
                      <span className="weakness-label">弱项维度：</span>
                      {alt.weakness_dimensions.map((w) => (
                        <span key={w} className="weakness-tag">{w}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {dataReadiness && dataReadiness.substitution_notes.length > 0 && (
        <div className="gap-section">
          <span className="label">替代建议</span>
          <ul className="missing-list">
            {dataReadiness.substitution_notes.map((note) => (
              <li key={note} className="missing-item">
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {unrecommendedExamples && unrecommendedExamples.length > 0 && (
        <div className="gap-section unrecommended-section">
          <span className="label">未推荐模型原因</span>
          <div className="unrecommended-list">
            {unrecommendedExamples.map((ex) => (
              <div key={ex.model_id} className="unrecommended-item">
                <span className="unrec-name">{ex.model_name}</span>
                <span className="unrec-reason">{ex.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default DataGapPanel;
