import React from 'react';
import type { ReportData } from '../types';

interface RecommendationReportProps {
  data: ReportData;
  onCopy: () => void;
  onDownload: () => void;
  onExport?: (format: 'docx' | 'pdf') => void;
  generating: boolean;
}

const RecommendationReport: React.FC<RecommendationReportProps> = ({
  data,
  onCopy,
  onDownload,
  onExport,
  generating,
}) => {
  if (!data) return null;

  const sections = data.sections ?? [];
  const handlePrint = () => window.print();

  return (
    <div className="card report-preview">
      <div className="report-header">
        <div>
          <h3 className="card-title">{data.title || '推荐报告'}</h3>
          {data.summary && <p className="report-summary">{data.summary}</p>}
        </div>
        <div className="report-actions">
          <button className="btn btn-secondary btn-sm" onClick={onCopy} disabled={generating}>
            复制
          </button>
          <button className="btn btn-secondary btn-sm" onClick={onDownload} disabled={generating}>
            下载 Markdown
          </button>
          {onExport && (
            <>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onExport('docx')}
                disabled={generating}
              >
                下载 DOCX
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onExport('pdf')}
                disabled={generating}
              >
                下载 PDF
              </button>
            </>
          )}
          <button className="btn btn-secondary btn-sm" onClick={handlePrint}>
            打印
          </button>
        </div>
      </div>

      {sections.length > 0 ? (
        <div className="report-content" id="report-content">
          {sections.map((section) => (
            <div className="report-section" key={section.title}>
              <h4>{section.title}</h4>
              <pre className="report-markdown-block">{section.content}</pre>
            </div>
          ))}
          <div className="report-footer">
            <p>报告编号：{data.report_id}</p>
            <p>生成时间：{new Date(data.generated_at).toLocaleString('zh-CN')}</p>
          </div>
        </div>
      ) : (
        <div className="report-content" id="report-content">
          <pre className="report-markdown-block">{data.raw_content || '暂无报告内容。'}</pre>
        </div>
      )}
    </div>
  );
};

export default RecommendationReport;
