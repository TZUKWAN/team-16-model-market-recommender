import React from 'react';
import type { SystemStatus } from '../types';

interface SystemStatusPanelProps {
  status: SystemStatus | null;
  loading: boolean;
  frontendMockEnabled: boolean;
  onRefresh: () => void;
}

const boolText = (value: boolean, yes = '已开启', no = '未开启') =>
  value ? yes : no;

const statusTone = (ok: boolean): 'ok' | 'warn' => (ok ? 'ok' : 'warn');

const SystemStatusPanel: React.FC<SystemStatusPanelProps> = ({
  status,
  loading,
  frontendMockEnabled,
  onRefresh,
}) => {
  const backendOnline = status?.status === 'healthy';
  const items = [
    {
      label: '认证模式',
      value: status?.auth_mode === 'real'
        ? `${status.auth_adapter ?? 'enterprise'} / ${status.production_auth_ready ? '生产就绪' : '未就绪'}`
        : 'Demo Header（非生产认证）',
      tone: status?.auth_mode === 'real' && status.production_auth_ready ? 'ok' : 'warn',
    },
    {
      label: '后端服务',
      value: loading ? '检查中' : backendOnline ? '健康' : '不可达',
      tone: statusTone(Boolean(backendOnline)),
    },
    {
      label: '官方数据集',
      value: boolText(Boolean(status?.official_dataset_loaded), '已加载', '未加载'),
      tone: statusTone(Boolean(status?.official_dataset_loaded)),
    },
    {
      label: '模型资产库',
      value: status?.model_asset_repository_ready
        ? `${status.model_asset_total ?? 0} 个模型`
        : '未就绪',
      tone: statusTone(Boolean(status?.model_asset_repository_ready)),
    },
    {
      label: '语义检索',
      value: status?.retrieval_runtime_mode === 'competition_dense'
        ? status.dense_available
          ? `BGE-M3 / ${status.dense_embedding_dimension ?? 0}维 / 清单${status.dense_manifest_verified ? '已校验' : '未校验'}`
          : `竞赛模式未就绪${status.dense_error_code ? ` / ${status.dense_error_code}` : ''}`
        : status?.dense_available
          ? `可选 BGE-M3 / ${status.dense_embedding_dimension ?? 0}维`
          : '轻量模式 / 稀疏检索',
      tone: status?.retrieval_runtime_mode === 'competition_dense'
        ? statusTone(Boolean(status.dense_runtime_ready && status.dense_manifest_verified))
        : 'warn',
    },
    {
      label: '大模型解析',
      value: status?.llm_enabled
        ? `${status.llm_provider} / ${status.llm_model}`
        : '未启用',
      tone: statusTone(Boolean(status?.llm_enabled)),
    },
    {
      label: 'LLM Key',
      value: boolText(Boolean(status?.llm_api_key_configured), '已配置', '未配置'),
      tone: statusTone(Boolean(status?.llm_api_key_configured)),
    },
    {
      label: '调用审计',
      value: boolText(Boolean(status?.llm_trace_enabled), '已开启', '未开启'),
      tone: statusTone(Boolean(status?.llm_trace_enabled)),
    },
    {
      label: '模型市场',
      value: status?.model_market_adapter
        ? `${status.model_market_adapter} / ${boolText(Boolean(status?.model_market_connected), '已连接', '未连接')}`
        : boolText(Boolean(status?.model_market_connected), '已连接', '未连接'),
      tone: statusTone(Boolean(status?.model_market_connected)),
    },
    {
      label: '市场适配器',
      value: status?.model_market_status_message ?? '未知',
      tone: status?.model_market_demo_mode ? 'warn' : statusTone(Boolean(status?.model_market_configured)),
    },
    {
      label: '结果模式',
      value: status?.demo_result_mode ? '演示/兜底' : '真实接口',
      tone: status?.demo_result_mode ? 'warn' : 'ok',
    },
    {
      label: '前端回退',
      value: frontendMockEnabled ? 'Mock 开启' : 'Mock 关闭',
      tone: frontendMockEnabled ? 'warn' : 'ok',
    },
    {
      label: '资产校验',
      value: `${status?.model_asset_validation_issues ?? 0} 个问题`,
      tone: (status?.model_asset_validation_issues ?? 0) > 0 ? 'warn' : 'ok',
    },
  ];

  return (
    <div className="card system-status-panel">
      <div className="panel-title-row">
        <h3 className="card-title">系统状态</h3>
        <button
          className="btn btn-secondary btn-sm"
          type="button"
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? '检查中' : '刷新'}
        </button>
      </div>

      <div className="status-grid">
        {items.map((item) => (
          <div className={`status-item status-${item.tone}`} key={item.label}>
            <span className="label">{item.label}</span>
            <span className="status-value">{item.value}</span>
          </div>
        ))}
      </div>

      {status?.error && (
        <p className="status-warning">健康检查失败：{status.error}</p>
      )}

      {status && !status.error && (
        <p className="status-meta">
          {status.app_name} v{status.version}，更新时间：
          {new Date(status.timestamp).toLocaleString('zh-CN')}
        </p>
      )}
    </div>
  );
};

export default SystemStatusPanel;
