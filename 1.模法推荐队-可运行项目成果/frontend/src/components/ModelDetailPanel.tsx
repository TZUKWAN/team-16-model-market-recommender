import React from 'react';
import type { ModelMetadata } from '../types';

interface ModelDetailPanelProps {
  model: ModelMetadata | null;
  loading: boolean;
  error: string | null;
}

const listText = (items?: string[]) => {
  if (!items || items.length === 0) return '无';
  return items.join('、');
};

const schemaFields = (schema?: Record<string, unknown>) => {
  const properties = schema?.properties;
  if (!properties || typeof properties !== 'object') return [];
  return Object.keys(properties as Record<string, unknown>);
};

const ModelDetailPanel: React.FC<ModelDetailPanelProps> = ({ model, loading, error }) => {
  if (loading) {
    return (
      <div className="card model-detail-panel">
        <h3 className="card-title">模型详情</h3>
        <p className="muted-text">正在加载模型资产详情...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card model-detail-panel">
        <h3 className="card-title">模型详情</h3>
        <p className="status-warning">模型详情加载失败：{error}</p>
      </div>
    );
  }

  if (!model) return null;

  const requiredFields = schemaFields(model.input_schema);
  const outputFields = schemaFields(model.output_schema);

  return (
    <div className="card model-detail-panel">
      <div className="model-detail-header">
        <div>
          <h3 className="card-title">模型详情</h3>
          <p className="model-detail-name">{model.model_name}</p>
        </div>
        <div className="model-detail-badges">
          <span className="detail-badge">{model.model_id}</span>
          <span className="detail-badge">{model.source || 'unknown'}</span>
          <span className={`detail-badge ${model.api_available ? 'ok' : 'warn'}`}>
            {model.api_available ? 'API 可用' : 'API 未配置'}
          </span>
        </div>
      </div>

      <div className="detail-grid">
        <div className="detail-item">
          <span className="label">业务域</span>
          <span>{model.domain}</span>
        </div>
        <div className="detail-item">
          <span className="label">资产状态</span>
          <span>{model.asset_status || model.deployment_status}</span>
        </div>
        <div className="detail-item">
          <span className="label">权限范围</span>
          <span>{model.permission_scope || '未声明'}</span>
        </div>
        <div className="detail-item">
          <span className="label">资产版本</span>
          <span>{model.asset_version || '未声明'}</span>
        </div>
      </div>

      <div className="detail-section">
        <span className="label">模型说明</span>
        <p className="detail-text">{model.description || '暂无说明'}</p>
      </div>

      <div className="schema-grid">
        <div className="schema-block">
          <span className="label">必需输入</span>
          <div className="field-list">
            {(requiredFields.length ? requiredFields : model.input_fields_required).map((field) => (
              <span className="field-chip required" key={field}>{field}</span>
            ))}
          </div>
        </div>
        <div className="schema-block">
          <span className="label">可选输入</span>
          <div className="field-list">
            {model.input_fields_optional.length > 0 ? (
              model.input_fields_optional.map((field) => (
                <span className="field-chip optional" key={field}>{field}</span>
              ))
            ) : (
              <span className="muted-text">无</span>
            )}
          </div>
        </div>
        <div className="schema-block">
          <span className="label">模型输出</span>
          <div className="field-list">
            {(outputFields.length ? outputFields : model.output_fields).map((field) => (
              <span className="field-chip output" key={field}>{field}</span>
            ))}
          </div>
        </div>
        <div className="schema-block">
          <span className="label">性能证据状态</span>
          <p className="muted-text">
            {model.field_provenance?.performance_metrics?.verification === 'source_verified'
              ? '已有来源核验记录；页面不展示内部数值，请以审计材料为准。'
              : '当前指标为未核验的演示草稿，页面不展示数值。'}
          </p>
        </div>
      </div>

      <div className="detail-section">
        <span className="label">适用场景</span>
        <p className="detail-text">{listText(model.business_scenario)}</p>
      </div>

      <div className="detail-section">
        <span className="label">合规与法律边界</span>
        <p className="detail-text">{model.legal_boundary || model.compliance_boundary || '未声明'}</p>
      </div>

      <div className="detail-section">
        <span className="label">不适用条件</span>
        <p className="detail-text">{model.unsuitable_conditions || '未声明'}</p>
      </div>
    </div>
  );
};

export default ModelDetailPanel;
