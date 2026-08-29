import React, { useState } from 'react';
import type { ModelInvokeResponse } from '../types';
import { invokeModel } from '../api/client';
import CompliancePanel from './CompliancePanel';
import ModelResultTable from './ModelResultTable';

interface ModelInvocationPanelProps {
  modelId: string;
  modelName: string;
  onResult?: (result: ModelInvokeResponse) => void;
}

const ModelInvocationPanel: React.FC<ModelInvocationPanelProps> = ({ modelId, modelName, onResult }) => {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ModelInvokeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleInvoke = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await invokeModel(modelId, {
        customer_profile: { demo_customer: true },
        transaction_flow: { demo_window_days: 90 },
      });
      setResult(response);
      onResult?.(response);
    } catch (err: any) {
      setError(err.message || '模型调用失败');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card model-invocation-panel">
      <div className="invocation-header">
        <div>
          <h3 className="card-title">模型调用演示：{modelName}</h3>
          <div className="invocation-subtitle">{modelId}</div>
        </div>
        <button
          type="button"
          className="btn btn-primary btn-small"
          onClick={handleInvoke}
          disabled={loading}
        >
          {loading ? '调用中...' : '调用模型'}
        </button>
      </div>

      {error && <div className="invocation-error">{error}</div>}

      {result && (
        <div className="invocation-result">
          <div className="invocation-badges">
            <span className={result.demo_data ? 'demo-badge' : 'real-badge'}>
              {result.demo_data ? '脱敏演示结果' : '真实接口结果'}
            </span>
            <span className="task-badge">任务：{result.task_id}</span>
            <span className="task-badge">状态：{result.status}</span>
          </div>
          {result.result?.desensitized_notice && (
            <p className="demo-notice">{result.result.desensitized_notice}</p>
          )}
          <CompliancePanel result={result.result} />
          <ModelResultTable result={result.result} modelId={modelId} />
        </div>
      )}
    </div>
  );
};

export default ModelInvocationPanel;
