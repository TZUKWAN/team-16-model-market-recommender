import React from 'react';
import type { ModelResultPayload } from '../types';

interface CompliancePanelProps {
  result: ModelResultPayload;
}

const CompliancePanel: React.FC<CompliancePanelProps> = ({ result }) => {
  const compliance = result.compliance;
  if (!result.compliance_notice && !result.usage_boundary && !compliance) return null;

  return (
    <div className="compliance-panel">
      <div className="compliance-header">
        <h4>合规与用途边界</h4>
        {compliance?.sensitivity_level && (
          <span className={`sensitivity-badge sensitivity-${compliance.sensitivity_level}`}>
            {compliance.sensitivity_level}
          </span>
        )}
      </div>
      {result.compliance_notice && (
        <p className="compliance-notice">{result.compliance_notice}</p>
      )}
      {result.usage_boundary && (
        <p className="usage-boundary">{result.usage_boundary}</p>
      )}
      <div className="compliance-grid">
        {compliance?.allowed_usage && compliance.allowed_usage.length > 0 && (
          <div>
            <span className="compliance-label">允许用途</span>
            <ul>
              {compliance.allowed_usage.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
        {compliance?.prohibited_usage && compliance.prohibited_usage.length > 0 && (
          <div>
            <span className="compliance-label">禁止用途</span>
            <ul>
              {compliance.prohibited_usage.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {compliance?.sensitive_fields_masked && compliance.sensitive_fields_masked.length > 0 && (
        <div className="masked-fields">
          <span className="compliance-label">已脱敏字段</span>
          <div className="masked-field-tags">
            {compliance.sensitive_fields_masked.map((field) => (
              <span key={field}>{field}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default CompliancePanel;
