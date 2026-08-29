import React, { useState, useCallback, useEffect } from 'react';
import { ClipboardCheck } from 'lucide-react';
import type {
  ParseDemandResponse,
  RecommendModelsResponse,
  ModelRecommendation,
  CompositionResponse,
  ReportData,
  EvaluationResponse,
  OfficialEvalSummary,
  OfficialDatasetInfo,
  ClarificationQuestion,
  SystemStatus,
  ModelMetadata,
  GraphNeighborhood,
  ModelInvokeResponse,
  CompareModelsResponse,
  FeedbackAction,
  FeedbackStatsResponse,
  SurveyAccess,
  SurveyScenario,
  RecommendationVersionRecord,
} from '../types';
import {
  parseDemand,
  recommendModels,
  recommendComposition,
  generateReport,
  getEvaluationMetrics,
  fetchOfficialEvaluationSummary,
  fetchOfficialDatasetInfo,
  getSystemStatus,
  getModelDetail,
  getModelGraph,
  graphMatchPath,
  getNodeNeighborhood,
  setMockFallback,
  isMockFallback,
  compareModels,
  submitFeedback,
  getFeedbackStats,
  exportReport,
  getRecommendationVersions,
} from '../api/client';
import DemandInput from '../components/DemandInput';
import SystemUnderstanding from '../components/SystemUnderstanding';
import ClarificationPanel from '../components/ClarificationPanel';
import RecommendationPanel from '../components/RecommendationPanel';
import EvidenceCards from '../components/EvidenceCards';
import DataGapPanel from '../components/DataGapPanel';
import ModelDetailPanel from '../components/ModelDetailPanel';
import KnowledgeGraphView from '../components/KnowledgeGraphView';
import ModelInvocationPanel from '../components/ModelInvocationPanel';
import CompositionFlow from '../components/CompositionFlow';
import ExplanationTabs from '../components/ExplanationTabs';
import RecommendationReport from '../components/RecommendationReport';
import RecommendationDiff from '../components/RecommendationDiff';
import EvaluationDashboard from '../components/EvaluationDashboard';
import OfficialDatasetDashboard from '../components/OfficialDatasetDashboard';
import SystemStatusPanel from '../components/SystemStatusPanel';
import ModelComparePanel from '../components/ModelComparePanel';
import AdoptionStats from '../components/AdoptionStats';
import ScenarioScriptPanel from '../components/ScenarioScriptPanel';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import EmptyState from '../components/EmptyState';
import SurveyPanel from '../components/SurveyPanel';
import RecommendationVersionHistory from '../components/RecommendationVersionHistory';

type AppStep = 'input' | 'parsing' | 'parsed' | 'recommending' | 'recommended' | 'composing' | 'composed' | 'reporting' | 'reported';

const createClientRequestId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const RECOMMENDATION_SESSION_STORAGE_KEY = 'model-market:last-recommendation-session';

const readStoredRecommendationSession = () => {
  if (typeof window === 'undefined') return '';
  try {
    return window.sessionStorage.getItem(RECOMMENDATION_SESSION_STORAGE_KEY) || '';
  } catch {
    return '';
  }
};

const persistRecommendationSession = (sessionId: string) => {
  if (typeof window === 'undefined') return;
  try {
    if (sessionId) {
      window.sessionStorage.setItem(RECOMMENDATION_SESSION_STORAGE_KEY, sessionId);
    } else {
      window.sessionStorage.removeItem(RECOMMENDATION_SESSION_STORAGE_KEY);
    }
  } catch {
    // Storage can be unavailable in hardened or private browser contexts.
  }
};

const MainPage: React.FC = () => {
  const [step, setStep] = useState<AppStep>('input');
  const [error, setError] = useState<string | null>(null);

  // Parse results
  const [parseResult, setParseResult] = useState<ParseDemandResponse | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<ClarificationQuestion[]>([]);
  // Multi-turn clarification session id (created by backend on first parse,
  // threaded through every subsequent clarification turn).
  const [sessionId, setSessionId] = useState<string>(readStoredRecommendationSession);

  // Recommendation results
  const [recommendResult, setRecommendResult] = useState<RecommendModelsResponse | null>(null);
  const [firstRoundRecommendations, setFirstRoundRecommendations] = useState<ModelRecommendation[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelRecommendation | null>(null);
  const [selectedModelDetail, setSelectedModelDetail] = useState<ModelMetadata | null>(null);
  const [modelDetailLoading, setModelDetailLoading] = useState(false);
  const [modelDetailError, setModelDetailError] = useState<string | null>(null);
  const [graphVisible, setGraphVisible] = useState(false);
  const [modelGraph, setModelGraph] = useState<GraphNeighborhood | null>(null);
  const [modelGraphLoading, setModelGraphLoading] = useState(false);
  const [modelGraphError, setModelGraphError] = useState<string | null>(null);
  const [graphPathNodeIds, setGraphPathNodeIds] = useState<string[]>([]);
  const [graphPathSummary, setGraphPathSummary] = useState<string>('');
  const [graphPathError, setGraphPathError] = useState<string | null>(null);
  const [graphDrillNode, setGraphDrillNode] = useState<string | null>(null);
  const [graphDrillData, setGraphDrillData] = useState<GraphNeighborhood | null>(null);
  const [graphDrillLoading, setGraphDrillLoading] = useState(false);
  const [latestModelResult, setLatestModelResult] = useState<ModelInvokeResponse | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareData, setCompareData] = useState<CompareModelsResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [feedbackStats, setFeedbackStats] = useState<FeedbackStatsResponse | null>(null);
  const [surveyOpen, setSurveyOpen] = useState(false);
  const [surveyAccess, setSurveyAccess] = useState<SurveyAccess>({ campaignId: '', invitationToken: '' });
  const [recommendationVersions, setRecommendationVersions] = useState<RecommendationVersionRecord[]>([]);
  const [recommendationVersionsLoading, setRecommendationVersionsLoading] = useState(false);
  const [recommendationVersionsError, setRecommendationVersionsError] = useState<string | null>(null);

  // Composition results
  const [compositionResult, setCompositionResult] = useState<CompositionResponse | null>(null);

  // Report
  const [reportData, setReportData] = useState<ReportData | null>(null);

  // Evaluation
  const [evaluationData, setEvaluationData] = useState<EvaluationResponse | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evaluationTab, setEvaluationTab] = useState<'system' | 'official'>('system');
  const [officialSummary, setOfficialSummary] = useState<OfficialEvalSummary | null>(null);
  const [officialDataset, setOfficialDataset] = useState<OfficialDatasetInfo | null>(null);
  const [officialEvalLoading, setOfficialEvalLoading] = useState(false);

  // System status
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [systemStatusLoading, setSystemStatusLoading] = useState(false);

  // Mock toggle
  const [, forceUpdate] = useState(0);

  const handleLoadSystemStatus = useCallback(async () => {
    setSystemStatusLoading(true);
    const result = await getSystemStatus();
    setSystemStatus(result);
    setSystemStatusLoading(false);
  }, []);

  useEffect(() => {
    handleLoadSystemStatus();
  }, [handleLoadSystemStatus]);

  const loadRecommendationVersions = useCallback(async (targetSessionId: string) => {
    if (!targetSessionId) {
      setRecommendationVersions([]);
      return;
    }
    setRecommendationVersionsLoading(true);
    setRecommendationVersionsError(null);
    try {
      const response = await getRecommendationVersions(targetSessionId);
      setRecommendationVersions(response.versions);
    } catch (err: any) {
      setRecommendationVersions([]);
      setRecommendationVersionsError(err.message || '加载推荐版本失败');
    } finally {
      setRecommendationVersionsLoading(false);
    }
  }, []);

  useEffect(() => {
    persistRecommendationSession(sessionId);
    if (sessionId) {
      void loadRecommendationVersions(sessionId);
    }
  }, [loadRecommendationVersions, sessionId]);

  const handleParse = useCallback(async (text: string) => {
    setError(null);
    setStep('parsing');
    setParseResult(null);
    setRecommendResult(null);
    setCompositionResult(null);
    setReportData(null);
    setSelectedModel(null);
    setSelectedModelDetail(null);
    setModelDetailError(null);
    setGraphVisible(false);
    setModelGraph(null);
    setModelGraphError(null);
    setLatestModelResult(null);
    setCompareIds([]);
    setCompareData(null);
    setCompareError(null);
    setSurveyOpen(false);
    setFirstRoundRecommendations([]);
    setRecommendationVersions([]);
    setRecommendationVersionsError(null);

    try {
      // Start a fresh conversation session on a new top-level demand.
      persistRecommendationSession('');
      setSessionId('');
      const result = await parseDemand(text, {}, '');
      if (result.session_id) {
        setSessionId(result.session_id);
      }
      setParseResult(result);
      setStep('parsed');
    } catch (err: any) {
      setError(err.message || '解析需求失败');
      setStep('input');
    }
  }, []);

  const handleClarificationResolve = useCallback(async (answers: ClarificationQuestion[]) => {
    if (!parseResult) return;
    setClarificationAnswers(answers);
    setError(null);
    setStep('parsing');
    setRecommendResult(null);
    setCompositionResult(null);
    setReportData(null);
    setSelectedModel(null);
    setSelectedModelDetail(null);
    setGraphVisible(false);
    setModelGraph(null);
    setModelGraphError(null);
    setLatestModelResult(null);
    setCompareIds([]);
    setCompareData(null);
    setCompareError(null);

    try {
      // Thread the backend-issued session_id back so the parser sees the full
      // multi-turn Q&A history instead of re-parsing from scratch.
      const result = await parseDemand(
        parseResult.raw_text,
        {
          clarification_answers: answers,
        },
        sessionId
      );
      if (result.session_id) {
        setSessionId(result.session_id);
      }
      setParseResult(result);
      setStep('parsed');
    } catch (err: any) {
      setError(err.message || '提交补充信息失败');
      setStep('parsed');
    }
  }, [parseResult, sessionId]);

  const handleRecommend = useCallback(async () => {
    if (!parseResult) return;
    setError(null);
    setStep('recommending');

    try {
      const result = await recommendModels({
        parse_result: parseResult,
        model_source: 'official_then_demo',
        top_k: 5,
        demo_top_k: 3,
        client_request_id: createClientRequestId(),
      });
      setRecommendResult(result);
      // Record first-round recommendations for multi-round diff comparison
      setFirstRoundRecommendations((prev) =>
        prev.length === 0 ? result.recommendations : prev
      );
      const initialModel = result.recommendations[0] || result.demo_references[0];
      if (initialModel) {
        setSelectedModel(initialModel);
      }
      const versionSessionId = parseResult.session_id || sessionId;
      if (versionSessionId) {
        await loadRecommendationVersions(versionSessionId);
      }
      setStep('recommended');
    } catch (err: any) {
      setError(err.message || '获取推荐失败');
      setStep('parsed');
    }
  }, [loadRecommendationVersions, parseResult, sessionId]);

  const handleSelectModel = useCallback((model: ModelRecommendation) => {
    setSelectedModel(model);
    setGraphVisible(false);
    setLatestModelResult(null);
  }, []);


  const handleToggleCompare = useCallback((model: ModelRecommendation) => {
    setCompareIds((prev) => {
      if (prev.includes(model.model_id)) {
        return prev.filter((id) => id !== model.model_id);
      }
      return [...prev, model.model_id].slice(-3);
    });
  }, []);

  const handleRemoveCompare = useCallback((modelId: string) => {
    setCompareIds((prev) => prev.filter((id) => id !== modelId));
  }, []);

  const handleClearCompare = useCallback(() => {
    setCompareIds([]);
    setCompareData(null);
    setCompareError(null);
  }, []);

  const handleFeedback = useCallback(async (
    model: ModelRecommendation,
    action: FeedbackAction,
    reason: string
  ) => {
    if (!recommendResult || !parseResult) return;
    try {
      await submitFeedback({
        request_id: recommendResult.request_id,
        model_id: model.model_id,
        model_name: model.model_name,
        action,
        reason,
        scenario: parseResult.business_scenario || parseResult.intent,
        parse_result: parseResult,
        metadata: {
          rank: model.rank,
          total_score: model.total_score,
          source: model.source,
          catalog_version: model.catalog_version,
        },
      });
      const stats = await getFeedbackStats();
      setFeedbackStats(stats);
    } catch (err: any) {
      setError(err.message || '记录反馈失败');
    }
  }, [recommendResult, parseResult]);
  const handleViewGraph = useCallback((model: ModelRecommendation) => {
    setSelectedModel(model);
    setGraphVisible(true);
    setLatestModelResult(null);
  }, []);


  useEffect(() => {
    if (!parseResult || compareIds.length < 2) {
      setCompareData(null);
      setCompareError(null);
      setCompareLoading(false);
      return;
    }

    let cancelled = false;
    setCompareLoading(true);
    setCompareError(null);

    compareModels({ model_ids: compareIds, parse_result: parseResult })
      .then((data) => {
        if (!cancelled) setCompareData(data);
      })
      .catch((err: any) => {
        if (!cancelled) {
          setCompareData(null);
          setCompareError(err.message || '生成模型对比失败');
        }
      })
      .finally(() => {
        if (!cancelled) setCompareLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [compareIds, parseResult]);
  useEffect(() => {
    if (!selectedModel) {
      setSelectedModelDetail(null);
      setModelDetailError(null);
      setModelGraph(null);
      setModelGraphError(null);
      return;
    }

    let cancelled = false;
    setModelDetailLoading(true);
    setModelDetailError(null);

    getModelDetail(selectedModel.model_id)
      .then((detail) => {
        if (!cancelled) setSelectedModelDetail(detail);
      })
      .catch((err: any) => {
        if (!cancelled) {
          setSelectedModelDetail(null);
          setModelDetailError(err.message || '获取模型详情失败');
        }
      })
      .finally(() => {
        if (!cancelled) setModelDetailLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedModel]);

  useEffect(() => {
    if (!selectedModel || !graphVisible) {
      return;
    }

    let cancelled = false;
    setModelGraphLoading(true);
    setModelGraphError(null);
    // Reset path highlight and drilldown when switching models.
    setGraphPathNodeIds([]);
    setGraphPathSummary('');
    setGraphPathError(null);
    setGraphDrillNode(null);
    setGraphDrillData(null);

    getModelGraph(selectedModel.model_id)
      .then((graph) => {
        if (!cancelled) setModelGraph(graph);
      })
      .catch((err: any) => {
        if (!cancelled) {
          setModelGraph(null);
          setModelGraphError(err.message || '获取模型图谱失败');
        }
      })
      .finally(() => {
        if (!cancelled) setModelGraphLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedModel, graphVisible]);

  // Fetch the demand→model match path for path highlight.
  useEffect(() => {
    if (!selectedModel || !graphVisible || !parseResult) {
      setGraphPathNodeIds([]);
      setGraphPathSummary('');
      return;
    }

    let cancelled = false;
    setGraphPathError(null);

    graphMatchPath(parseResult as unknown as Record<string, unknown>, selectedModel.model_id)
      .then((result) => {
        if (cancelled) return;
        setGraphPathNodeIds(result.matched_node_ids);
        setGraphPathSummary(result.summary);
      })
      .catch((err: any) => {
        if (cancelled) return;
        // Path highlight failure should not block the graph view.
        setGraphPathNodeIds([]);
        setGraphPathSummary('');
        setGraphPathError(err.message || '路径匹配失败，仅展示模型邻接关系。');
      });

    return () => {
      cancelled = true;
    };
  }, [selectedModel, graphVisible, parseResult]);

  // Drill into a node's 1-hop neighborhood (F4.2).
  const handleGraphDrillDown = useCallback((nodeId: string) => {
    setGraphDrillNode(nodeId);
    setGraphDrillData(null);
    setGraphDrillLoading(true);
    getNodeNeighborhood(nodeId)
      .then((data) => {
        setGraphDrillData(data);
      })
      .catch(() => {
        // Drilldown failure: keep drill node selected but show no sub-graph.
        setGraphDrillData(null);
      })
      .finally(() => {
        setGraphDrillLoading(false);
      });
  }, []);

  const handleGraphResetDrill = useCallback(() => {
    setGraphDrillNode(null);
    setGraphDrillData(null);
  }, []);

  const handleCompose = useCallback(async () => {
    if (!parseResult) return;
    setError(null);
    setStep('composing');

    try {
      const result = await recommendComposition(parseResult);
      setCompositionResult(result);
      setStep('composed');
    } catch (err: any) {
      setError(err.message || '获取组合方案失败');
      setStep('recommended');
    }
  }, [parseResult]);

  const handleGenerateReport = useCallback(async () => {
    if (!parseResult || !recommendResult) return;
    setError(null);
    setStep('reporting');

    try {
      const result = await generateReport({
        request_id: recommendResult.request_id,
        demand_raw: parseResult.raw_text,
        parse_result: parseResult,
        recommend_result: recommendResult,
        composition_result: compositionResult ?? undefined,
        model_result: latestModelResult ?? undefined,
        include_details: true,
      });
      setReportData(result);
      setStep('reported');
    } catch (err: any) {
      setError(err.message || '生成报告失败');
      setStep('composed');
    }
  }, [parseResult, recommendResult, compositionResult, latestModelResult]);

  const handleCopyReport = useCallback(() => {
    if (!reportData) return;
    const content = generateMarkdown(reportData);
    navigator.clipboard.writeText(content).then(() => {
      alert('报告已复制到剪贴板');
    });
  }, [reportData]);

  const handleDownloadReport = useCallback(() => {
    if (!reportData) return;
    const content = generateMarkdown(reportData);
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `recommendation-report-${reportData.report_id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [reportData]);

  const handleExportReport = useCallback(
    async (format: 'docx' | 'pdf') => {
      if (!reportData || !parseResult || !recommendResult) return;
      try {
        const blob = await exportReport(
          {
            request_id: recommendResult.request_id,
            demand_raw: parseResult.raw_text,
            parse_result: parseResult,
            recommend_result: recommendResult,
            composition_result: compositionResult ?? undefined,
            model_result: latestModelResult ?? undefined,
          },
          format
        );
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `recommendation-report-${reportData.report_id}.${format}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (err: any) {
        setError(err?.message || '导出报告失败');
      }
    },
    [reportData, parseResult, recommendResult, compositionResult, latestModelResult]
  );

  const handleLoadEvaluation = useCallback(async () => {
    setEvalLoading(true);
    setEvalError(null);
    try {
      const result = await getEvaluationMetrics();
      setEvaluationData(result);
    } catch (err: any) {
      setEvalError(err.message || '获取评估指标失败');
    } finally {
      setEvalLoading(false);
    }
  }, []);

  const handleLoadOfficialEvaluation = useCallback(async () => {
    setOfficialEvalLoading(true);
    setError(null);
    try {
      const [summary, dataset] = await Promise.all([
        fetchOfficialEvaluationSummary(),
        fetchOfficialDatasetInfo(),
      ]);
      setOfficialSummary(summary);
      setOfficialDataset(dataset);
    } catch (err: any) {
      setError(err.message || '加载官方数据集评估失败');
    } finally {
      setOfficialEvalLoading(false);
    }
  }, []);

  const handleToggleMock = useCallback(() => {
    setMockFallback(!isMockFallback());
    forceUpdate((n) => n + 1);
    handleLoadSystemStatus();
  }, [handleLoadSystemStatus]);

  return (
    <div className="main-page">
      {/* Header */}
      <header className="app-header">
        <div className="header-left">
          <h1 className="app-title">银行模型市场智能推荐助手</h1>
          <p className="app-subtitle">自然语言需求 → 智能模型推荐 → 组合方案 → 报告导出</p>
        </div>
        <div className="header-right">
          <label className="mock-toggle">
            <input
              type="checkbox"
              checked={isMockFallback()}
              onChange={handleToggleMock}
            />
            <span>前端 Mock 回退</span>
          </label>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <ErrorState message={error} onRetry={() => setError(null)} />
      )}

      {/* Main Content */}
      <div className="app-content">
        {/* Left Column - Input & Understanding */}
        <div className="content-left">
          <DemandInput onParse={handleParse} loading={step === 'parsing'} />

          {step === 'parsing' && <LoadingState message="正在解析需求..." />}

          {parseResult && (
            <>
              <SystemUnderstanding data={parseResult} />

              <ClarificationPanel
                questions={parseResult.clarification_questions}
                onResolve={handleClarificationResolve}
                disabled={step === 'parsing'}
              />
            </>
          )}

          {/* Recommendation Section */}
          {(step === 'parsed' || step === 'recommending' || step === 'recommended' || step === 'composing' || step === 'composed' || step === 'reporting' || step === 'reported') && (
            <div className="action-section">
              <button
                className="btn btn-primary btn-large"
                onClick={handleRecommend}
                disabled={step === 'recommending'}
              >
                {step === 'recommending' ? '正在推荐...' : '生成模型推荐'}
              </button>
            </div>
          )}

          {step === 'recommending' && <LoadingState message="正在获取模型推荐..." />}

          {recommendResult && (
            <>
              <div className="recommendation-policy-summary" role="status">
                <strong>当前目录策略：</strong>
                官方模型形成主榜；Demo 模型仅作为独立参考，不计入官方评估和组合推荐。
                {recommendResult.summary && <span>{recommendResult.summary}</span>}
              </div>
              <RecommendationPanel
                recommendations={recommendResult.recommendations}
                selectedModelId={selectedModel?.model_id ?? null}
                onSelectModel={handleSelectModel}
                onViewGraph={handleViewGraph}
                compareModelIds={compareIds}
                onToggleCompare={handleToggleCompare}
                onFeedback={handleFeedback}
                title={`官方推荐 Top${recommendResult.recommendations.length}`}
                description="主榜只使用官方 60 模型，排名、版本记录、评估指标与组合推荐均以此为准。"
              />

              {recommendResult.demo_reference_status === 'available' && (
                <RecommendationPanel
                  recommendations={recommendResult.demo_references}
                  selectedModelId={selectedModel?.model_id ?? null}
                  onSelectModel={handleSelectModel}
                  onViewGraph={handleViewGraph}
                  compareModelIds={compareIds}
                  onToggleCompare={handleToggleCompare}
                  onFeedback={handleFeedback}
                  title={`Demo 参考候选 ${recommendResult.demo_references.length} 个`}
                  description="来自脱敏 Demo 目录，可查看详情、图谱、调用和对比；仅用于能力展示与方案参考，不替代官方推荐。"
                  variant="demo"
                />
              )}

              {recommendResult.demo_reference_status === 'unavailable' && (
                <div className="demo-reference-unavailable" role="status">
                  Demo 参考目录当前不可用；官方推荐结果保持不变，系统未回退到模拟模型。
                </div>
              )}

              <div className="action-section survey-launcher">
                <button type="button" className="btn btn-secondary" onClick={() => setSurveyOpen(true)}>
                  <ClipboardCheck size={18} />评价推荐解释
                </button>
              </div>

              <ModelComparePanel
                data={compareData}
                selectedIds={compareIds}
                loading={compareLoading}
                error={compareError}
                onRemove={handleRemoveCompare}
                onClear={handleClearCompare}
              />

              {selectedModel && (
                <>
                  <ModelDetailPanel
                    model={selectedModelDetail}
                    loading={modelDetailLoading}
                    error={modelDetailError}
                  />
                  <ModelInvocationPanel
                    modelId={selectedModel.model_id}
                    modelName={selectedModel.model_name}
                    onResult={setLatestModelResult}
                  />
                  {graphVisible && (
                    <KnowledgeGraphView
                      graph={modelGraph}
                      modelName={selectedModel.model_name}
                      loading={modelGraphLoading}
                      error={modelGraphError}
                      pathNodeIds={graphPathNodeIds}
                      pathSummary={graphPathSummary}
                      pathError={graphPathError}
                      drillNode={graphDrillNode}
                      drillData={graphDrillData}
                      drillLoading={graphDrillLoading}
                      onDrillDown={handleGraphDrillDown}
                      onResetDrill={handleGraphResetDrill}
                    />
                  )}
                  <EvidenceCards
                    evidenceCards={selectedModel.evidence_cards}
                    modelName={selectedModel.model_name}
                  />
                  <DataGapPanel
                    requiredData={selectedModel.required_data}
                    missingData={selectedModel.missing_data}
                    alternativeModels={selectedModel.alternative_models}
                    dataReadiness={selectedModel.data_readiness}
                    unrecommendedExamples={recommendResult.unrecommended_examples}
                  />
                </>
              )}
            </>
          )}

          {/* Composition Section */}
          {(step === 'recommended' || step === 'composing' || step === 'composed' || step === 'reporting' || step === 'reported') && (
            <div className="action-section">
              <button
                className="btn btn-primary btn-large"
                onClick={handleCompose}
                disabled={step === 'composing'}
              >
                {step === 'composing' ? '正在生成组合方案...' : '生成组合方案'}
              </button>
            </div>
          )}

          {step === 'composing' && <LoadingState message="正在生成组合方案..." />}

          {compositionResult && (
            <>
              <CompositionFlow data={compositionResult} />
              <ExplanationTabs
                businessExplanation={compositionResult.business_explanation}
                technicalExplanation={compositionResult.technical_explanation}
                managementExplanation={compositionResult.management_explanation}
                compositionName={compositionResult.composition_name}
              />
            </>
          )}

          {/* Report Section */}
          {(step === 'composed' || step === 'reporting' || step === 'reported') && (
            <div className="action-section">
              <button
                className="btn btn-primary btn-large"
                onClick={handleGenerateReport}
                disabled={step === 'reporting'}
              >
                {step === 'reporting' ? '正在生成报告...' : '生成一页纸报告'}
              </button>
            </div>
          )}

          {step === 'reporting' && <LoadingState message="正在生成报告..." />}

          {reportData && (
            <RecommendationReport
              data={reportData}
              onCopy={handleCopyReport}
              onDownload={handleDownloadReport}
              onExport={handleExportReport}
              generating={false}
            />
          )}

          {firstRoundRecommendations.length > 0 && recommendResult && (
            <RecommendationDiff
              firstRound={firstRoundRecommendations}
              finalRound={recommendResult.recommendations}
            />
          )}

          {sessionId && (recommendResult || recommendationVersions.length > 0) && (
            <RecommendationVersionHistory
              sessionId={sessionId}
              versions={recommendationVersions}
              loading={recommendationVersionsLoading}
              error={recommendationVersionsError}
              onRefresh={() => loadRecommendationVersions(sessionId)}
            />
          )}
        </div>

        {/* Right Column - Evaluation Dashboard */}
        <div className="content-right">
          <SystemStatusPanel
            status={systemStatus}
            loading={systemStatusLoading}
            frontendMockEnabled={isMockFallback()}
            onRefresh={handleLoadSystemStatus}
          />

          <AdoptionStats data={feedbackStats} />

          <ScenarioScriptPanel parseResult={parseResult as unknown as Record<string, unknown> | null} />

          <div className="tabs-header evaluation-tabs-header">
            <button
              className={`tab-btn ${evaluationTab === 'system' ? 'active' : ''}`}
              onClick={() => setEvaluationTab('system')}
            >
              系统评估
            </button>
            <button
              className={`tab-btn ${evaluationTab === 'official' ? 'active' : ''}`}
              onClick={() => {
                setEvaluationTab('official');
                if (!officialSummary && !officialEvalLoading) {
                  void handleLoadOfficialEvaluation();
                }
              }}
            >
              官方数据集
            </button>
          </div>

          {evaluationTab === 'system' && (
            <>
              <div className="action-section">
                <button
                  className="btn btn-secondary btn-large"
                  onClick={handleLoadEvaluation}
                  disabled={evalLoading}
                >
                  {evalLoading ? '加载中...' : '加载评估指标'}
                </button>
              </div>

              {evalLoading && <LoadingState message="正在获取评估指标..." />}

              {evalError && !evalLoading && (
                <ErrorState message={evalError} onRetry={handleLoadEvaluation} />
              )}

              {evaluationData && (
                <EvaluationDashboard
                  data={evaluationData}
                  loading={evalLoading}
                  onRefresh={handleLoadEvaluation}
                />
              )}

              {!evaluationData && !evalLoading && !evalError && (
                <EmptyState
                  message="尚未加载评估指标"
                  hint={'点击"加载评估指标"按钮查看系统性能数据'}
                />
              )}
            </>
          )}

          {evaluationTab === 'official' && (
            <>
              {officialEvalLoading && <LoadingState message="正在加载官方数据集..." />}

              {officialSummary && officialDataset && (
                <OfficialDatasetDashboard
                  summary={officialSummary}
                  dataset={officialDataset}
                />
              )}

              {!officialSummary && !officialEvalLoading && (
                <EmptyState
                  message="尚未加载官方数据集"
                  hint="切换到官方数据集标签将自动加载数据"
                />
              )}
            </>
          )}
        </div>
      </div>

      {recommendResult && parseResult && (
        <SurveyPanel
          open={surveyOpen}
          sampleId={recommendResult.request_id}
          scenarioId={toSurveyScenario(parseResult.intent)}
          access={surveyAccess}
          onAccessChange={setSurveyAccess}
          onClose={() => setSurveyOpen(false)}
        />
      )}
    </div>
  );
};

function toSurveyScenario(intent: string): SurveyScenario {
  if (intent === 'credit_risk' || intent === 'customer_marketing' || intent === 'operation_management') {
    return intent;
  }
  return 'operation_management';
}

function generateMarkdown(data: ReportData): string {
  if (data.raw_content) {
    return `# ${data.title || '模型推荐报告'}\n\n${data.raw_content}\n\n---\n*报告编号：${data.report_id}，生成时间：${new Date(data.generated_at).toLocaleString('zh-CN')}*`;
  }

  let md = `# 模型推荐报告\n\n`;
  md += `**报告编号：** ${data.report_id}  \n`;
  md += `**生成时间：** ${new Date(data.generated_at).toLocaleString('zh-CN')}\n\n`;

  md += `## 用户需求\n\n${data.user_demand || ''}\n\n`;

  md += `## 系统理解\n\n`;
  md += `- **意图：** ${data.system_understanding?.intent || ''}\n`;
  md += `- **领域：** ${data.system_understanding?.domain || ''}\n`;
  md += `- **场景：** ${data.system_understanding?.scenario || ''}\n`;
  md += `- **标签：** ${(data.system_understanding?.tags ?? []).join('、')}\n`;
  md += `- **业务→模型翻译：** ${data.system_understanding?.translation || ''}\n\n`;

  md += `## Top3 推荐模型\n\n`;
  md += `| 排名 | 模型名称 | 推荐理由 |\n`;
  md += `|------|----------|----------|\n`;
  for (const m of data.top3_models ?? []) {
    md += `| ${m.rank} | ${m.model_name} | ${m.reason} |\n`;
  }
  md += `\n`;

  if (data.best_composition) {
    md += `## 最佳组合方案\n\n`;
    md += `- **名称：** ${data.best_composition.name}\n`;
    md += `- **流程：** ${data.best_composition.steps.join(' → ')}\n\n`;
  }

  md += `## 所需数据与缺口\n\n`;
  md += `- **所需数据：** ${(data.required_data ?? []).join('、')}\n`;
  if ((data.data_gaps ?? []).length > 0) {
    md += `- **数据缺口：** ${(data.data_gaps ?? []).join('、')}\n`;
  }
  md += `\n`;

  md += `## 实施步骤\n\n`;
  (data.implementation_steps ?? []).forEach((s, i) => {
    md += `${i + 1}. ${s}\n`;
  });
  md += `\n`;

  md += `## 风险提示\n\n`;
  (data.risk_tips ?? []).forEach((t) => {
    md += `- ${t}\n`;
  });
  md += `\n`;

  md += `---\n`;
  md += `*该报告由银行模型市场智能推荐助手自动生成*\n`;

  return md;
}

export default MainPage;
