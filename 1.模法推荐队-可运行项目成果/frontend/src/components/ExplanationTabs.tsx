import React, { useState } from 'react';

interface ExplanationTabsProps {
  businessExplanation: string;
  technicalExplanation: string;
  managementExplanation: string;
  compositionName?: string;
}

type TabKey = 'business' | 'technical' | 'management';

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: 'business', label: '业务版', icon: '👔' },
  { key: 'technical', label: '技术版', icon: '⚙' },
  { key: 'management', label: '管理版', icon: '📊' },
];

const ExplanationTabs: React.FC<ExplanationTabsProps> = ({
  businessExplanation,
  technicalExplanation,
  managementExplanation,
  compositionName,
}) => {
  const [activeTab, setActiveTab] = useState<TabKey>('business');

  const contentMap: Record<TabKey, string> = {
    business: businessExplanation,
    technical: technicalExplanation,
    management: managementExplanation,
  };

  const activeContent = contentMap[activeTab];

  if (!activeContent) return null;

  return (
    <div className="card explanation-tabs">
      <h3 className="card-title">
        解释模式
        {compositionName && <span className="explanation-subtitle">：{compositionName}</span>}
      </h3>

      <div className="tabs-header">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      <div className="tab-content">
        <p>{activeContent}</p>
      </div>
    </div>
  );
};

export default ExplanationTabs;
