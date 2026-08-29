import React from 'react';

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

const ErrorState: React.FC<ErrorStateProps> = ({ message, onRetry }) => {
  return (
    <div className="error-state">
      <div className="error-icon">⚠</div>
      <p className="error-message">{message}</p>
      {onRetry && (
        <button className="btn btn-secondary" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
};

export default ErrorState;
