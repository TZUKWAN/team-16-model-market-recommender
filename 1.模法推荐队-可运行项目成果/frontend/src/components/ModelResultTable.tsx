import React, { useMemo, useState } from 'react';
import type { ModelResultPayload } from '../types';

interface ModelResultTableProps {
  result: ModelResultPayload;
  modelId: string;
}

function csvEscape(value: unknown): string {
  let text = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(text)) {
    text = `'${text}`;
  }
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

const ModelResultTable: React.FC<ModelResultTableProps> = ({ result, modelId }) => {
  const [filter, setFilter] = useState('');
  const rows = result.rows ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const filteredRows = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter((row) =>
      Object.values(row).some((value) => String(value ?? '').toLowerCase().includes(query))
    );
  }, [filter, rows]);

  const handleExport = () => {
    if (columns.length === 0) return;
    const lines = [
      columns.map(csvEscape).join(','),
      ...filteredRows.map((row) => columns.map((column) => csvEscape(row[column])).join(',')),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${modelId}-result.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (rows.length === 0) {
    return <p className="empty-result-text">暂无可展示结果明细。</p>;
  }

  return (
    <div className="model-result-table">
      <div className="result-table-toolbar">
        <input
          type="search"
          className="result-filter-input"
          placeholder="筛选结果..."
          aria-label="筛选模型调用结果"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <button type="button" className="btn btn-secondary btn-small" onClick={handleExport}>
          导出 CSV
        </button>
      </div>
      <div className="invocation-table-wrap">
        <table className="invocation-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column}>{String(row[column] ?? '')}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="result-table-count">
        显示 {filteredRows.length} / {rows.length} 条
      </div>
    </div>
  );
};

export default ModelResultTable;
