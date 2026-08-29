import React from 'react';
import type { CompositionExecutionNode, CompositionResponse, UsageGuide } from '../types';

interface CompositionFlowProps {
  data: CompositionResponse;
}

function shortValue(value: unknown): string {
  if (Array.isArray(value)) return value.slice(0, 4).join('、');
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function normalizeGuide(guide: UsageGuide | string, index: number): UsageGuide {
  if (typeof guide === 'string') {
    return {
      step: `Step ${index + 1}`,
      description: guide,
    };
  }
  return guide;
}

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成',
  degraded: '降级完成',
  blocked: '已阻塞',
  failed: '执行失败',
  pending: '等待执行',
  partially_blocked: '部分阻塞',
  no_executable_node: '无法执行',
};

function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status;
}

const CompositionFlow: React.FC<CompositionFlowProps> = ({ data }) => {
  if (!data || !data.nodes || data.nodes.length === 0) return null;
  const execution = data.execution_result;
  const executionByNode = new Map<string, CompositionExecutionNode>();
  execution?.nodes.forEach((node) => {
    executionByNode.set(node.node_id, node);
  });
  const actualOutputs = Array.from(new Set(
    (execution?.nodes || [])
      .filter((node) => !['blocked', 'failed'].includes(node.status))
      .flatMap((node) => {
        const fields = node.output_snapshot.generated_fields;
        return Array.isArray(fields) ? fields.map(String) : [];
      })
  ));
  const hasBlockedNode = (execution?.nodes || []).some((node) =>
    ['blocked', 'failed'].includes(node.status)
  );

  return (
    <div className="card composition-flow">
      <h3 className="card-title">
        {data.composition_name}
      </h3>
      <p className="composition-scenario">场景：{data.scenario}</p>

      {/* Flow Diagram */}
      <div className="flow-diagram">
        {data.nodes.map((node, idx) => (
          <React.Fragment key={node.node_id || node.step_id || node.model_id}>
            <div className="flow-node">
              <div className="flow-node-header">
                <span className="flow-step-badge">Step {node.step_order}</span>
                <span className="flow-capability">{node.capability}</span>
              </div>
              <div className="flow-node-body">
                <div className="flow-model-name">{node.model_name}</div>
                <div className="flow-model-id">{node.model_id}</div>
                <div className="flow-io">
                  <div className="flow-inputs">
                    <span className="io-label">输入</span>
                    <div className="io-tags">
                      {(node.input_fields || node.input_requirements || []).map((f) => (
                        <span key={f} className="io-tag input-tag">{f}</span>
                      ))}
                    </div>
                  </div>
                  <div className="flow-outputs">
                    <span className="io-label">输出</span>
                    <div className="io-tags">
                      {node.output_fields.map((f) => (
                        <span key={f} className="io-tag output-tag">{f}</span>
                      ))}
                    </div>
                  </div>
                </div>
                {(() => {
                  const executionNode = executionByNode.get(node.node_id || node.step_id || '');
                  if (!executionNode) return null;
                  return (
                    <div className="execution-node-panel">
                      <div className="execution-node-header">
                        <span className={`execution-status status-${executionNode.status}`}>
                          {statusLabel(executionNode.status)}
                        </span>
                        <span>{executionNode.elapsed_ms} ms</span>
                      </div>
                      {executionNode.status_reason && (
                        <p className="execution-status-reason">{executionNode.status_reason}</p>
                      )}
                      <div className="execution-snapshots">
                        <div>
                          <span className="io-label">执行输入</span>
                          <div className="snapshot-grid">
                            {Object.entries(executionNode.input_snapshot).slice(0, 4).map(([key, value]) => (
                              <div key={key} className="snapshot-row">
                                <span>{key}</span>
                                <strong>{shortValue(value)}</strong>
                              </div>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="io-label">执行输出</span>
                          <div className="snapshot-grid">
                            {Object.entries(executionNode.output_snapshot)
                              .filter(([key]) => key !== 'demo_data')
                              .slice(0, 5)
                              .map(([key, value]) => (
                                <div key={key} className="snapshot-row">
                                  <span>{key}</span>
                                  <strong>{shortValue(value)}</strong>
                                </div>
                              ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
            {idx < data.nodes.length - 1 && (
              <div className="flow-arrow-container">
                <div className="flow-arrow">↓</div>
                {data.flow_edges
                  .filter((e) =>
                    e.from_step === node.step_id ||
                    e.source_node_id === node.node_id
                  )
                  .map((edge) => (
                    <div
                      key={`${edge.from_step || edge.source_node_id}-${edge.to_step || edge.target_node_id}`}
                      className="flow-edge-reason"
                    >
                      {edge.reason || edge.suggestion || edge.io_status || '节点输出传递到下一节点'}
                    </div>
                  ))}
                {execution?.edges
                  .filter((edge) => edge.source_node_id === node.node_id)
                  .map((edge) => (
                    <div key={`exec-${edge.source_node_id}-${edge.target_node_id}`} className="execution-edge-reason">
                      {statusLabel(edge.status)}：{edge.transferred_fields.slice(0, 4).join('、') || edge.note}
                    </div>
                  ))}
              </div>
            )}
          </React.Fragment>
        ))}
      </div>

      {execution && (
        <div className="execution-result-section">
          <div className="execution-summary-header">
            <h4 className="subsection-title">组合执行结果</h4>
            <span className={`execution-status status-${execution.status}`}>
              {statusLabel(execution.status)}
            </span>
          </div>
          <p className="execution-notice">{execution.desensitized_notice}</p>
          <div className="fused-result-grid">
            {Object.entries(execution.fused_result)
              .filter(([key]) => !['demo_data', 'desensitized_notice', 'confidence'].includes(key))
              .map(([key, value]) => (
                <div key={key} className="fused-result-item">
                  <span>{key}</span>
                  <strong>{shortValue(value)}</strong>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* IO Compatibility */}
      {data.io_compatibility && Object.keys(data.io_compatibility).length > 0 && (
        <div className="io-compatibility-section">
          <h4 className="subsection-title">输入输出兼容性</h4>
          <div className="compat-summary">
            总边数：{data.io_compatibility.total_edges}，通过：{data.io_compatibility.passed}，部分：{data.io_compatibility.partial}，失败：{data.io_compatibility.failed}，兼容率：{(data.io_compatibility.compatibility_rate * 100).toFixed(0)}%
          </div>
          {Object.entries(data.io_compatibility)
            .filter(([key]) => key.includes('->'))
            .map(([key, comp]) => {
              if (!comp || typeof comp !== 'object') return null;
              return (
                <div key={key} className="io-compat-item">
                  <div className="compat-header">{key}</div>
                  {Array.isArray(comp.matched) && comp.matched.length > 0 && (
                    <div className="compat-matched">
                      <span className="compat-label">✓ 已匹配：</span>
                      {comp.matched.join('、')}
                    </div>
                  )}
                  {Array.isArray(comp.unmatched) && comp.unmatched.length > 0 && (
                    <div className="compat-unmatched">
                      <span className="compat-label">⚠ 未匹配：</span>
                      {comp.unmatched.join('、')}
                    </div>
                  )}
                  {comp.notes && <div className="compat-notes">{comp.notes}</div>}
                </div>
              );
            })}
        </div>
      )}

      {/* Missing Data */}
      {data.missing_data.length > 0 && (
        <div className="composition-missing">
          <h4 className="subsection-title">数据缺口</h4>
          <div className="missing-tags">
            {data.missing_data.map((d) => (
              <span key={d} className="data-tag missing">⚠ {d}</span>
            ))}
          </div>
        </div>
      )}

      {execution && actualOutputs.length > 0 && (
        <div className="composition-outputs">
          <h4 className="subsection-title">实际可用输出</h4>
          <div className="output-tags">
            {actualOutputs.map((output) => (
              <span key={output} className="data-tag available">✓ {output}</span>
            ))}
          </div>
          {hasBlockedNode && (
            <p className="execution-output-note">阻塞节点没有产生输出，未计入以上列表。</p>
          )}
        </div>
      )}

      {/* Planned Outputs */}
      {data.expected_outputs.length > 0 && (
        <div className="composition-outputs">
          <h4 className="subsection-title">计划产出</h4>
          <div className="output-tags">
            {data.expected_outputs.map((o) => (
              <span key={o} className="data-tag planned">○ {o}</span>
            ))}
          </div>
        </div>
      )}

      {/* Usage Guide */}
      {data.usage_guide && data.usage_guide.length > 0 && (
        <div className="usage-guide">
          <h4 className="subsection-title">使用指南</h4>
          {data.usage_guide.map((item, index) => {
            const guide = normalizeGuide(item, index);
            return (
              <div key={`${guide.step}-${index}`} className="usage-step">
                <div className="usage-step-title">{guide.step}</div>
                <p className="usage-step-desc">{guide.description}</p>
                {(guide.estimated_time || guide.data_preparation) && (
                  <div className="usage-step-meta">
                    {guide.estimated_time && <span>预计时间：{guide.estimated_time}</span>}
                    {guide.data_preparation && <span>数据准备：{guide.data_preparation}</span>}
                  </div>
                )}
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default CompositionFlow;
