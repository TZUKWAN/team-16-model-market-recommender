import type {
  ParseDemandResponse,
  RecommendModelsRequest,
  RecommendModelsResponse,
  CompositionResponse,
  ReportRequest,
  ReportData,
  EvaluationResponse,
  OfficialEvalSummary,
  OfficialEvalResults,
  OfficialEvalFailure,
  OfficialDatasetInfo,
  SystemStatus,
  ModelMetadata,
  GraphNeighborhood,
  GraphMatchPathResponse,
  ModelInvokeResponse,
  CompareModelsRequest,
  CompareModelsResponse,
  FeedbackRequest,
  FeedbackResponse,
  FeedbackStatsResponse,
  ScenarioMatchRequest,
  ScenarioMatchResponse,
  ScriptGenerateRequest,
  ScriptGenerateResponse,
  BusinessScenario,
  SurveyDefinitionResponse,
  SurveySubmissionRequest,
  SurveySubmissionResponse,
  RecommendationVersionListResponse,
  RecommendationVersionDiffResponse,
} from '../types';

import {
  parseMock,
  recommendMock,
  compositionMock,
  reportMock,
  evaluationMock,
  officialEvalSummaryMock,
  officialEvalResultsValMock,
  officialEvalResultsTestMock,
  officialEvalFailuresMock,
  officialDatasetInfoMock,
} from '../mocks';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Set to true to use mock data when backend is unavailable
let useMockFallback =
  import.meta.env.VITE_USE_MOCK === 'true';
let workflowCorrelationId = '';

function newCorrelationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `workflow-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function correlationHeaders(): Record<string, string> {
  return workflowCorrelationId ? { 'X-Correlation-ID': workflowCorrelationId } : {};
}

export function setMockFallback(enabled: boolean) {
  useMockFallback = enabled;
}

export function isMockFallback(): boolean {
  return useMockFallback;
}

function frontendFallbackStatus(error?: unknown): SystemStatus {
  const message = error instanceof Error ? error.message : String(error ?? '');
  return {
    status: 'unreachable',
    version: 'unknown',
    app_name: '银行模型市场智能推荐助手',
    timestamp: new Date().toISOString(),
    mock_mode: useMockFallback,
    auth_mode: 'demo',
    auth_adapter: 'unreachable',
    auth_configured: false,
    production_auth_ready: false,
    official_dataset_loaded: false,
    model_market_connected: false,
    model_market_adapter: 'unreachable',
    model_market_demo_mode: true,
    model_market_configured: false,
    model_market_status_message: '后端不可达，无法确认模型市场适配器状态。',
    demo_result_mode: true,
    model_asset_repository_ready: false,
    model_asset_total: 0,
    model_asset_by_source: {},
    model_asset_by_domain: {},
    model_asset_validation_issues: 0,
    llm_trace_enabled: false,
    llm_enabled: false,
    llm_provider: 'unknown',
    llm_model: 'unknown',
    llm_base_url_configured: false,
    llm_api_key_configured: false,
    llm_timeout_seconds: 0,
    llm_max_retries: 0,
    error: message || '后端健康检查不可达',
  };
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...correlationHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API Error ${res.status}: ${errorText}`);
  }
  return res.json();
}

async function apiGet<T>(path: string, timeoutMs: number = 15_000): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: correlationHeaders(),
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`API Error ${res.status}: ${errorText}`);
    }
    return res.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`请求超时（${Math.round(timeoutMs / 1000)}秒），请稍后重试`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

/** 自然语言需求解析 */
export async function parseDemand(
  rawText: string,
  context: Record<string, unknown> = {},
  sessionId: string = ''
): Promise<ParseDemandResponse> {
  if (!sessionId) {
    workflowCorrelationId = newCorrelationId();
  }
  if (useMockFallback) {
    const answers = Array.isArray(context.clarification_answers)
      ? context.clarification_answers
        .map((item: any) => item?.user_answer || '')
        .filter(Boolean)
        .join(' ')
      : '';
    const mockText = answers ? `${rawText} ${answers}` : rawText;
    return {
      ...parseMock(mockText),
      raw_text: rawText,
      parse_source: 'rule',
      llm_enabled: false,
      llm_trace_id: null,
    };
  }
  return apiPost<ParseDemandResponse>('/api/v1/parse-demand', {
    raw_text: rawText,
    context,
    session_id: sessionId,
  });
}

/** 获取后端真实系统状态 */
export async function getSystemStatus(): Promise<SystemStatus> {
  if (useMockFallback) {
    return frontendFallbackStatus('前端 Mock 回退已开启');
  }
  try {
    return await apiGet<SystemStatus>('/api/v1/health');
  } catch (err) {
    console.warn('获取系统状态失败:', err);
    return frontendFallbackStatus(err);
  }
}

/** 单模型推荐 */
export async function recommendModels(
  request: RecommendModelsRequest
): Promise<RecommendModelsResponse> {
  if (useMockFallback) {
    return recommendMock(request);
  }
  return apiPost<RecommendModelsResponse>(
    '/api/v1/recommend-models',
    request
  );
}

/** 获取模型资产详情 */
export async function getModelDetail(modelId: string): Promise<ModelMetadata> {
  if (useMockFallback) {
    return {
      model_id: modelId,
      model_name: modelId,
      domain: 'demo',
      business_scenario: ['脱敏演示场景'],
      business_stage: ['demo'],
      customer_segment: [],
      model_capability: [],
      input_fields_required: [],
      input_fields_optional: [],
      output_fields: [],
      performance_metrics: {},
      applicable_conditions: '前端 Mock 回退开启，未读取真实后端模型资产。',
      unsuitable_conditions: '',
      compliance_boundary: '仅用于前端脱敏演示，不代表真实生产模型。',
      deployment_status: 'frontend_mock',
      api_available: false,
      historical_cases: [],
      tags: [],
      description: '前端 Mock 回退模型详情。',
      source: 'frontend_mock',
      asset_version: 'demo',
      asset_status: 'demo',
      permission_scope: 'frontend_mock_only',
      legal_boundary: '不可用于生产决策。',
      input_schema: { type: 'object', required: [], properties: {} },
      output_schema: { type: 'object', required: [], properties: {} },
      result_schema: { type: 'object', properties: {} },
    };
  }
  return apiGet<ModelMetadata>(`/api/v1/models/${encodeURIComponent(modelId)}`);
}

/** 获取模型知识图谱上下文 */
export async function getModelGraph(modelId: string): Promise<GraphNeighborhood> {
  if (useMockFallback) {
    return {
      center_node_id: `model:${modelId}`,
      nodes: [
        {
          node_id: `model:${modelId}`,
          node_type: 'model',
          name: modelId,
          properties: { source: 'frontend_mock' },
        },
        {
          node_id: 'scenario:frontend_mock',
          node_type: 'scenario',
          name: '前端 Mock 场景',
          properties: {},
        },
      ],
      edges: [
        {
          edge_id: `edge:applies_to:model:${modelId}->scenario:frontend_mock`,
          source: `model:${modelId}`,
          target: 'scenario:frontend_mock',
          relation_type: 'applies_to',
          weight: 0.5,
          evidence: { source: 'frontend_mock' },
        },
      ],
    };
  }
  return apiGet<GraphNeighborhood>(`/api/v1/graph/model/${encodeURIComponent(modelId)}`);
}

/** 获取需求→模型的图谱路径证据 */
export async function graphMatchPath(
  parseResult: Record<string, unknown>,
  modelId: string,
  maxEdges: number = 80
): Promise<GraphMatchPathResponse> {
  if (useMockFallback) {
    return {
      model_id: modelId,
      matched_node_ids: [`model:${modelId}`],
      nodes: [
        {
          node_id: `model:${modelId}`,
          node_type: 'model',
          name: modelId,
          properties: { source: 'frontend_mock' },
        },
      ],
      edges: [],
      summary: '前端 Mock 回退：路径证据不可用。',
    };
  }
  return apiPost<GraphMatchPathResponse>('/api/v1/graph/match-path', {
    parse_result: parseResult,
    model_id: modelId,
    max_edges: maxEdges,
  });
}

/** 获取任意节点的邻居子图（用于下钻） */
export async function getNodeNeighborhood(nodeId: string): Promise<GraphNeighborhood> {
  if (useMockFallback) {
    return {
      center_node_id: nodeId,
      nodes: [
        {
          node_id: nodeId,
          node_type: 'model',
          name: nodeId,
          properties: { source: 'frontend_mock' },
        },
      ],
      edges: [],
    };
  }
  return apiGet<GraphNeighborhood>(
    `/api/v1/graph/node/${encodeURIComponent(nodeId)}`
  );
}

/** 调用模型并返回演示/真实结果 */
export async function invokeModel(
  modelId: string,
  inputData: Record<string, unknown> = {}
): Promise<ModelInvokeResponse> {
  if (useMockFallback) {
    return {
      model_id: modelId,
      task_id: `frontend-demo-${modelId}`,
      status: 'completed',
      demo_data: true,
      submitted_at: new Date().toISOString(),
      message: '前端 Mock 回退开启，返回脱敏演示结果。',
      result: {
        model_id: modelId,
        demo_data: true,
        result_type: 'frontend_mock',
        input_echo_keys: Object.keys(inputData),
        desensitized_notice: '前端 Mock 脱敏演示数据，不代表真实生产结果。',
        rows: [
          {
            demo_data: true,
            entity_id: 'FRONTEND_DEMO_0001',
            score: 0.82,
            suggested_action: '请连接后端后查看真实 demo 适配器结果。',
          },
        ],
      },
    };
  }
  return apiPost<ModelInvokeResponse>(`/api/v1/models/${encodeURIComponent(modelId)}/invoke`, {
    input_data: inputData,
    async_mode: true,
    request_context: {
      caller: 'frontend_demo',
    },
  });
}


/** 模型横向对比与效果预估 */
export async function compareModels(
  request: CompareModelsRequest
): Promise<CompareModelsResponse> {
  if (useMockFallback) {
    const items = request.model_ids.map((id) => ({
      model_id: id,
      model_name: id,
      domain: 'frontend_mock',
      customer_segment: ['mock_segment'],
      input_fields_required: ['customer_profile'],
      output_fields: ['score'],
      performance_metrics: { auc: 0.82 },
      applicable_conditions: '前端 Mock 回退开启，未读取真实对比数据。',
      unsuitable_conditions: '不可用于生产决策。',
      compliance_boundary: '仅用于前端脱敏演示。',
      data_readiness: {
        readiness_score: 80,
        required_fields: ['customer_profile'],
        available_fields: ['customer_profile'],
        missing_required_fields: [],
        missing_optional_fields: [],
        confidence_impact: 'Mock 数据。',
        action_items: [],
        substitution_notes: [],
      },
      effect_estimate: {
        estimated_lift_pct: 18,
        coverage_pct: 70,
        confidence_band_pct: [12, 24],
        data_readiness_factor: 0.8,
        segment_match_factor: 1,
        basis: ['前端 Mock 预估'],
        disclaimer: '基于模型历史指标的预估值，非真实调用结果。',
      },
    }));
    return {
      request_id: 'cmp-frontend-mock',
      items,
      matrix: [
        { dimension: '数据就绪度', values: Object.fromEntries(items.map((item) => [item.model_id, `${item.data_readiness.readiness_score}%`])) },
        { dimension: '预期提升', values: Object.fromEntries(items.map((item) => [item.model_id, `${item.effect_estimate.estimated_lift_pct}%`])) },
      ],
      disclaimer: 'Mock 对比数据，非真实评估结果。',
    };
  }
  return apiPost<CompareModelsResponse>('/api/v1/compare-models', request);
}

/** 记录采纳/不采纳/收藏反馈 */
export async function submitFeedback(
  request: FeedbackRequest
): Promise<FeedbackResponse> {
  if (useMockFallback) {
    return { event_id: `FDB_FRONTEND_${Date.now()}`, status: 'recorded' };
  }
  return apiPost<FeedbackResponse>('/api/v1/feedback', request);
}

/** 获取采纳统计 */
export async function getFeedbackStats(): Promise<FeedbackStatsResponse> {
  if (useMockFallback) {
    return { total_events: 0, items: [], human_event_count: 0, demo_event_count: 0, test_event_count: 0 };
  }
  return apiGet<FeedbackStatsResponse>('/api/v1/feedback/stats');
}

/** 加载真人解释理解度问卷定义。 */
export async function getSurveyDefinition(campaignId: string): Promise<SurveyDefinitionResponse> {
  if (useMockFallback) {
    throw new Error('真人问卷必须连接后端，不能在前端 Mock 模式提交。');
  }
  return apiGet<SurveyDefinitionResponse>(
    `/api/v1/surveys/campaigns/${encodeURIComponent(campaignId)}`
  );
}

/** 提交匿名真人问卷。邀请码只发送给问卷接口。 */
export async function submitSurveyResponse(
  request: SurveySubmissionRequest
): Promise<SurveySubmissionResponse> {
  if (useMockFallback) {
    throw new Error('真人问卷必须连接后端，不能使用 Mock 数据。');
  }
  return apiPost<SurveySubmissionResponse>('/api/v1/surveys/responses', request);
}

/** 场景匹配 — 需求→最相关业务场景 */
export async function matchScenarios(
  request: ScenarioMatchRequest
): Promise<ScenarioMatchResponse> {
  return apiPost<ScenarioMatchResponse>('/api/v1/scenarios/match', request);
}

/** 生成场景话术 — LLM 生成（mock 模式降级返回典型话术） */
export async function generateScenarioScript(
  request: ScriptGenerateRequest
): Promise<ScriptGenerateResponse> {
  return apiPost<ScriptGenerateResponse>(
    `/api/v1/scenarios/${request.scenario_id}/generate-script`,
    request
  );
}

/** 获取场景列表 */
export async function getScenarios(domain: string = ''): Promise<BusinessScenario[]> {
  const query = domain ? `?domain=${encodeURIComponent(domain)}` : '';
  return apiGet<BusinessScenario[]>(`/api/v1/scenarios${query}`);
}

/** 导出报告为 DOCX 或 PDF 文件（返回二进制 Blob） */
export async function exportReport(
  request: ReportRequest,
  format: 'docx' | 'pdf'
): Promise<Blob> {
  const url = `${API_BASE_URL}/api/v1/reports/recommendation/export?format=${format}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API Error ${res.status}: ${errorText}`);
  }
  return res.blob();
}

/** 获取推荐版本列表（F5.1） */
export async function getRecommendationVersions(
  sessionId: string
): Promise<RecommendationVersionListResponse> {
  return apiGet<RecommendationVersionListResponse>(
    `/api/v1/recommendation-versions/${encodeURIComponent(sessionId)}`
  );
}

/** 比较两个推荐版本（F5.1） */
export async function diffRecommendationVersions(
  sessionId: string,
  versionA: string,
  versionB: string
): Promise<RecommendationVersionDiffResponse> {
  return apiGet<RecommendationVersionDiffResponse>(
    `/api/v1/recommendation-versions/${encodeURIComponent(sessionId)}/diff?version_a=${encodeURIComponent(versionA)}&version_b=${encodeURIComponent(versionB)}`
  );
}

/** 组合推荐 */
export async function recommendComposition(
  parseResult: ParseDemandResponse | string
): Promise<CompositionResponse> {
  const query = typeof parseResult === 'string' ? parseResult : parseResult.raw_text;
  if (useMockFallback) {
    return compositionMock(query);
  }
  return apiPost<CompositionResponse>('/api/v1/recommend-composition', {
    parse_result: typeof parseResult === 'string' ? { raw_text: query } : parseResult,
    model_source: 'official',
    top_k: 3,
  });
}

/** 生成报告 */
export async function generateReport(
  request: ReportRequest
): Promise<ReportData> {
  if (useMockFallback) {
    return reportMock(request);
  }
  return apiPost<ReportData>('/api/v1/reports/recommendation', request);
}

/** 获取评估指标 */
export async function getEvaluationMetrics(): Promise<EvaluationResponse> {
  if (useMockFallback) {
    return evaluationMock();
  }
  const data = await apiGet<EvaluationResponse>('/api/v1/evaluation/metrics', 10_000);
  if (!data || !Array.isArray(data.metrics)) {
    throw new Error('评估指标返回格式不正确，请检查后端评估报告');
  }
  return data;
}

// ========== Official Dataset Evaluation ==========

export async function fetchOfficialEvaluationSummary(): Promise<OfficialEvalSummary> {
  if (useMockFallback) {
    return officialEvalSummaryMock();
  }
  return apiGet<OfficialEvalSummary>('/api/v1/official-evaluation/summary');
}

export async function fetchOfficialEvaluationResults(
  split: 'val' | 'test'
): Promise<OfficialEvalResults> {
  if (useMockFallback) {
    return split === 'val' ? officialEvalResultsValMock() : officialEvalResultsTestMock();
  }
  return apiGet<OfficialEvalResults>(
    `/api/v1/official-evaluation/results?split=${split}`
  );
}

export async function fetchOfficialEvaluationFailures(
  split?: 'val' | 'test',
  failureType?: string
): Promise<OfficialEvalFailure[]> {
  const params = new URLSearchParams();
  if (split) params.set('split', split);
  if (failureType) params.set('failure_type', failureType);
  const query = params.toString();
  if (useMockFallback) {
    return officialEvalFailuresMock(split, failureType);
  }
  return apiGet<OfficialEvalFailure[]>(
    `/api/v1/official-evaluation/failures${query ? `?${query}` : ''}`
  );
}

export async function fetchOfficialDatasetInfo(): Promise<OfficialDatasetInfo> {
  if (useMockFallback) {
    return officialDatasetInfoMock();
  }
  return apiGet<OfficialDatasetInfo>('/api/v1/official-evaluation/dataset');
}
