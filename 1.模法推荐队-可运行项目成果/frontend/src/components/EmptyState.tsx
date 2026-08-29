import React from 'react';

interface EmptyStateProps {
  message?: string;
  hint?: string;
}

const EmptyState: React.FC<EmptyStateProps> = ({
  message = '暂无数据',
  hint,
}) => {
  return (
    <div className="empty-state">
      <div className="empty-icon">📋</div>
      <p className="empty-message">{message}</p>
      {hint && <p className="empty-hint">{hint}</p>}
    </div>
  );
};

export default EmptyState;
