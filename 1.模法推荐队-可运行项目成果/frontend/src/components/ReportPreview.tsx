import React from 'react';
import type { ReportData } from '../types';

interface ReportPreviewProps {
  data: ReportData;
  onCopy: () => void;
  onDownload: () => void;
  generating: boolean;
}

const ReportPreview: React.FC<ReportPreviewProps> = ({
  data,
  onCopy,
  onDownload,
  generating,
}) => {
  if (!data) return null;

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="card report-preview">
      <div className="report-header">
        <h3 className="card-title">一页纸推荐报告</h3>
        <div className="report-actions">
          <button className="btn btn-secondary btn-sm" onClick={onCopy} disabled={generating}>
            📋 复制
          </button>
          <button className="btn btn-secondary btn-sm" onClick={onDownload} disabled={generating}>
            ⬇ 下载 Markdown
          </button>
          <button className="btn btn-secondary btn-sm" onClick={handlePrint}>
            🖨 打印/PDF
          </button>
        </div>
      </div>

      <div className="report-content" id="report-content">
        <div className="report-section">
          <h4>用户需求</h4>
          <p>{data.user_demand}</p>
        </div>

        <div className="report-section">
          <h4>系统理解</h4>
          <div className="report-understanding-grid">
            <div><strong>意图：</strong>{data.system_understanding?.intent}</div>
            <div><strong>领域：</strong>{data.system_understanding?.domain}</div>
            <div><strong>场景：</strong>{data.system_understanding?.scenario}</div>
            <div><strong>标签：</strong>{(data.system_understanding?.tags ?? []).join('、')}</div>
            <div className="report-full-width">
              <strong>业务→模型翻译：</strong>
              <p>{data.system_understanding?.translation}</p>
            </div>
          </div>
        </div>

        <div className="report-section">
          <h4>Top3 推荐模型</h4>
          <table className="report-table">
            <thead>
              <tr>
                <th>排名</th>
                <th>模型名称</th>
                <th>推荐理由</th>
              </tr>
            </thead>
            <tbody>
              {(data.top3_models ?? []).map((m) => (
                <tr key={m.rank}>
                  <td>{m.rank}</td>
                  <td>{m.model_name}</td>
                  <td>{m.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data.best_composition && (
          <div className="report-section">
            <h4>最佳组合方案</h4>
            <p><strong>名称：</strong>{data.best_composition.name}</p>
            <p><strong>流程：</strong>{data.best_composition.steps.join(' → ')}</p>
          </div>
        )}

        <div className="report-section">
          <h4>所需数据与缺口</h4>
          <p><strong>所需数据：</strong>{(data.required_data ?? []).join('、')}</p>
          {(data.data_gaps ?? []).length > 0 && (
            <p className="report-gap"><strong>数据缺口：</strong>{(data.data_gaps ?? []).join('、')}</p>
          )}
        </div>

        <div className="report-section">
          <h4>实施步骤</h4>
          <ol>
            {(data.implementation_steps ?? []).map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </div>

        <div className="report-section">
          <h4>风险提示</h4>
          <ul>
            {(data.risk_tips ?? []).map((tip, i) => (
              <li key={i}>{tip}</li>
            ))}
          </ul>
        </div>

        <div className="report-footer">
          <p>报告编号：{data.report_id}</p>
          <p>生成时间：{new Date(data.generated_at).toLocaleString('zh-CN')}</p>
        </div>
      </div>
    </div>
  );
};

export default ReportPreview;
