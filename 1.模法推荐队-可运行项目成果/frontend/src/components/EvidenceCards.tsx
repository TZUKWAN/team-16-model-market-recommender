import React, { useState } from 'react';
import type { EvidenceCard } from '../types';

interface EvidenceCardsProps {
  evidenceCards: EvidenceCard[];
  modelName: string;
}

const EvidenceCards: React.FC<EvidenceCardsProps> = ({ evidenceCards, modelName }) => {
  const [expanded, setExpanded] = useState(false);

  if (!evidenceCards || evidenceCards.length === 0) return null;

  const displayedCards = expanded ? evidenceCards : evidenceCards.slice(0, 3);

  return (
    <div className="card evidence-cards">
      <h3 className="card-title">证据卡片：{modelName}</h3>
      <div className="evidence-list">
        {displayedCards.map((card, idx) => {
          const text = card.evidence_text || card.content || '';
          const source = card.source_field || card.source || 'recommendation_evidence';
          return (
          <div key={idx} className="evidence-item">
            <div className="evidence-header">
              <span className="evidence-type">{card.evidence_type}</span>
            </div>
            <p className="evidence-text">{text}</p>
            <span className="evidence-source">来源：{source}</span>
          </div>
          );
        })}
      </div>
      {evidenceCards.length > 3 && (
        <button
          className="btn btn-text"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '收起' : `展开全部（共${evidenceCards.length}条）`}
        </button>
      )}
    </div>
  );
};

export default EvidenceCards;
