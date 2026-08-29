import React, { useState, useEffect, useCallback } from 'react';
import type {
  ScenarioMatchItem,
  ScriptGenerateResponse,
} from '../types';
import { matchScenarios, generateScenarioScript } from '../api/client';

interface Props {
  parseResult: Record<string, unknown> | null;
}

const DOMAIN_LABELS: Record<string, string> = {
  credit_risk: '风控',
  customer_marketing: '营销',
  operation_management: '运营',
};

const ScenarioScriptPanel: React.FC<Props> = ({ parseResult }) => {
  const [matches, setMatches] = useState<ScenarioMatchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>('');
  const [script, setScript] = useState<ScriptGenerateResponse | null>(null);
  const [scriptLoading, setScriptLoading] = useState(false);
  const [scriptType, setScriptType] = useState<string>('comprehensive');
  const [copied, setCopied] = useState(false);

  const runMatch = useCallback(async () => {
    if (!parseResult) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await matchScenarios({ parse_result: parseResult, top_k: 3 });
      setMatches(resp.matches);
      if (resp.matches.length > 0) {
        setSelectedId(resp.matches[0].scenario.scenario_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '场景匹配失败');
    } finally {
      setLoading(false);
    }
  }, [parseResult]);

  useEffect(() => {
    if (parseResult) {
      runMatch();
    }
  }, [parseResult, runMatch]);

  const handleGenerate = useCallback(async () => {
    if (!parseResult || !selectedId) return;
    setScriptLoading(true);
    setScript(null);
    try {
      const resp = await generateScenarioScript({
        scenario_id: selectedId,
        parse_result: parseResult,
        script_type: scriptType,
      });
      setScript(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : '话术生成失败');
    } finally {
      setScriptLoading(false);
    }
  }, [parseResult, selectedId, scriptType]);

  const handleCopy = useCallback(() => {
    if (script?.script.content) {
      navigator.clipboard.writeText(script.script.content).catch(() => {});
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [script]);

  if (!parseResult) {
    return (
      <div className="scenario-panel empty-state">
        <p>请先解析需求，再查看匹配的业务场景与生成话术。</p>
      </div>
    );
  }

  return (
    <div className="scenario-panel">
      <h3>业务场景匹配与话术生成</h3>
      <p className="panel-hint">
        系统根据需求匹配业务场景，并生成可落地的营销文案/风控说明/触达话术，从"推荐模型"升级到"推荐可落地方案"。
      </p>

      {loading && <div className="loading-state">匹配场景中...</div>}
      {error && <div className="error-state">⚠ {error}</div>}

      {!loading && matches.length > 0 && (
        <>
          <div className="scenario-matches">
            {matches.map((m) => (
              <div
                key={m.scenario.scenario_id}
                className={`scenario-item ${selectedId === m.scenario.scenario_id ? 'selected' : ''}`}
                onClick={() => setSelectedId(m.scenario.scenario_id)}
                role="button"
                tabIndex={0}
              >
                <div className="scenario-header">
                  <span className="scenario-name">{m.scenario.name}</span>
                </div>
                <div className="scenario-meta">
                  <span className="scenario-domain">
                    {DOMAIN_LABELS[m.scenario.domain] || m.scenario.domain}
                  </span>
                  {m.matched_keywords.length > 0 && (
                    <span className="scenario-keywords">
                      命中: {m.matched_keywords.slice(0, 5).join('、')}
                    </span>
                  )}
                </div>
                <div className="scenario-reason">{m.match_reason}</div>
              </div>
            ))}
          </div>

          <div className="script-controls">
            <select
              value={scriptType}
              onChange={(e) => setScriptType(e.target.value)}
              aria-label="话术类型"
            >
              <option value="comprehensive">综合话术</option>
              <option value="marketing">营销文案</option>
              <option value="risk_notice">风控说明</option>
              <option value="outreach">触达话术</option>
            </select>
            <button
              onClick={handleGenerate}
              disabled={!selectedId || scriptLoading}
              className="generate-btn"
            >
              {scriptLoading ? '生成中...' : '生成话术'}
            </button>
          </div>

          {script && (
            <div className="script-result">
              <div className="script-header">
                <span className="script-title">
                  {script.script.scenario_name} · {script.script.script_type}
                </span>
                <button onClick={handleCopy} className="copy-btn">
                  {copied ? '✓ 已复制' : '复制'}
                </button>
              </div>
              <pre className="script-content">{script.script.content}</pre>
              <div className="script-disclaimer">
                ⚠ {script.script.disclaimer}
                {script.script.llm_used ? '（LLM实时生成）' : '（典型话术模板）'}
              </div>
            </div>
          )}
        </>
      )}

      {!loading && matches.length === 0 && !error && (
        <div className="empty-state">未匹配到业务场景。</div>
      )}
    </div>
  );
};

export default ScenarioScriptPanel;
