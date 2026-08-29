# API 契约文档

## 基本信息

| 项目 | 值 |
|------|-----|
| 基础路径 | `/api/v1` |
| 数据格式 | JSON |
| 认证方式 | 暂未启用 |
| 文档地址 | `/docs` (Swagger UI) / `/redoc` (ReDoc) |
| OpenAPI | `/openapi.json` |

## 端点总览

| 方法 | 路径 | 描述 | 当前实现 | 责任人 |
|------|------|------|----------|--------|
| GET | `/health` | 健康检查 | Mock | Agent A |
| POST | `/parse-demand` | 自然语言需求解析 | Mock → Agent C | Agent C |
| POST | `/recommend-models` | 单模型 TopK 推荐 | Mock → Agent C | Agent C |
| POST | `/recommend-composition` | 多模型组合编排 | Mock → Agent C | Agent C |
| GET | `/models/{model_id}` | 模型详情 | Mock → Agent B | Agent B |
| POST | `/reports/recommendation` | 推荐报告生成 | Mock → Agent D | Agent D |
| GET | `/evaluation/metrics` | 评估指标 | Mock → Agent C/D | Agent C/D |

## 请求/响应定义

### GET /api/v1/health

**响应：**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "app_name": "model-market-assistant",
  "timestamp": "2026-06-23T10:00:00Z",
  "mock_mode": true
}
```

### POST /api/v1/parse-demand

**请求：**
```json
{
  "raw_text": "我想筛一批县域新客，做首贷营销，最好能给出转化概率高的名单。",
  "context": {}
}
```

**响应：**
```json
{
  "raw_text": "...",
  "normalized_query": "...",
  "intent": "customer_marketing",
  "intent_confidence": 0.92,
  "domain": "客户营销",
  "business_scenario": "县域新客首贷营销",
  "business_stage": "贷前营销",
  "customer_segment": ["县域新客"],
  "product_type": ["首贷"],
  "risk_type": [],
  "expected_outputs": ["营销名单", "转化概率", "客户排序"],
  "constraints": [],
  "data_conditions": ["客户画像", "交易流水"],
  "tags": ["新客", "首贷", "营销转化", "响应预测"],
  "tag_confidence": {"新客": 0.91},
  "missing_slots": [],
  "need_clarification": false,
  "clarification_questions": [],
  "structured_filters": {},
  "business_to_model_translation": "...",
  "user_confirmable_summary": "..."
}
```

### POST /api/v1/recommend-models

**请求：**
```json
{
  "parse_result": {},
  "top_k": 5,
  "prefer_api_available": false,
  "prefer_landing_cases": false
}
```

**响应：**
```json
{
  "request_id": "rec-001",
  "recommendations": [
    {
      "model_id": "MKT_001",
      "model_name": "县域新客首贷转化预测模型",
      "rank": 1,
      "total_score": 91.5,
      "score_breakdown": {
        "scenario_match": 94.0,
        "customer_match": 92.0,
        "data_match": 88.0,
        "output_match": 93.0,
        "performance": 90.0,
        "landing_experience": 89.0,
        "compliance": 95.0
      },
      "recommendation_reason": "...",
      "evidence_cards": [],
      "required_data": [],
      "missing_data": [],
      "output_fields": [],
      "applicable_boundary": "...",
      "unsuitable_conditions": "...",
      "compliance_notes": "...",
      "alternative_models": []
    }
  ],
  "unrecommended_examples": [],
  "summary": "..."
}
```

### POST /api/v1/recommend-composition

**请求：**
```json
{
  "parse_result": {},
  "top_k": 3
}
```

**响应：**
```json
{
  "composition_id": "COMP_LOAN_PRE_001",
  "composition_name": "小微企业贷前风控组合",
  "scenario": "贷前风控",
  "total_score": 86.5,
  "nodes": [],
  "flow_edges": [],
  "io_compatibility": {},
  "missing_data": [],
  "expected_outputs": [],
  "business_explanation": "...",
  "technical_explanation": "...",
  "management_explanation": "...",
  "usage_guide": []
}
```

### GET /api/v1/models/{model_id}

**响应：**
```json
{
  "model_id": "MKT_001",
  "model_name": "县域新客首贷转化预测模型",
  "domain": "客户营销",
  "business_scenario": ["县域新客首贷营销"],
  "business_stage": ["贷前营销"],
  "customer_segment": ["县域新客"],
  "model_capability": ["转化预测"],
  "input_fields_required": [],
  "input_fields_optional": [],
  "output_fields": [],
  "performance_metrics": {},
  "applicable_conditions": "...",
  "unsuitable_conditions": "...",
  "compliance_boundary": "...",
  "deployment_status": "mock_available",
  "api_available": false,
  "historical_cases": [],
  "tags": [],
  "description": "..."
}
```

### POST /api/v1/reports/recommendation

**请求：**
```json
{
  "request_id": "rec-001",
  "format": "markdown",
  "include_details": true
}
```

**响应：**
```json
{
  "report_id": "rpt-001",
  "request_id": "rec-001",
  "generated_at": "2026-06-23T10:00:00Z",
  "format": "markdown",
  "title": "...",
  "summary": "...",
  "sections": [],
  "raw_content": "..."
}
```

### GET /api/v1/evaluation/metrics

**响应：**
```json
{
  "overall": {
    "intent_accuracy": 0.93,
    "tag_conversion_accuracy": 0.90,
    "top3_hit_rate": 0.87,
    "top5_hit_rate": 0.93,
    "composition_fitness": 0.82
  },
  "by_scenario": [],
  "details": [],
  "last_updated": "2026-06-23T10:00:00Z",
  "total_models_covered": 105,
  "total_samples": 270
}
```

## Mock 替换说明

当前所有端点均返回 Mock 数据。替换步骤：

1. Agent C 接管 `/parse-demand`、`/recommend-models`、`/recommend-composition`：
   - 修改 `app/api/v1/parse_demand.py`、`recommend_models.py`、`recommend_composition.py`
   - 将 Mock 函数替换为真实服务调用
   - 保持请求/响应 Schema 不变

2. Agent B 提供模型数据：
   - 修改 `app/api/v1/model_detail.py` 中的 `MOCK_MODELS` 字典
   - 或替换为数据库/外部 API 查询

3. Agent D 增强报告生成：
   - 修改 `app/api/v1/reports.py`

## Schema 稳定性保证

- 所有 Schema 字段仅做向后兼容新增
- 不删除或重命名已有字段
- 默认值保持空列表/空字符串/0/false
