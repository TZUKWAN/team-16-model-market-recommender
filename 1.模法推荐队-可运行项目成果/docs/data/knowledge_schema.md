# 模型元数据 Schema 说明

## 1. 概述

本文档定义模型市场智能推荐助手中所有模型元数据的字段结构、类型约束和必填规则。所有模型元数据统一存储在 `data/knowledge/` 目录下，以 `{domain}_{id}.json` 格式命名。

**⚠ 声明：所有数据均为模拟/脱敏样例数据，不包含任何真实客户信息。**

---

## 2. 模型元数据字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model_id` | string | ✅ | 模型唯一标识，格式：`{domain}_{3位数字}`，如 RISK_001 |
| `model_name` | string | ✅ | 模型中文名称，体现业务含义 |
| `domain` | string | ✅ | 业务领域枚举值：`credit_risk` / `customer_marketing` / `operation_management` |
| `business_scenario` | array[string] | ✅ | 业务场景描述列表，如 `["农户小额贷款贷前准入"]` |
| `business_stage` | array[string] | ✅ | 业务环节枚举值（可多选），详见标签体系 |
| `customer_segment` | array[string] | ✅ | 目标客群标签列表，详见标签体系 |
| `model_capability` | array[string] | ✅ | 模型能力标签列表，详见标签体系 |
| `input_fields_required` | array[string] | ✅ | 必填输入数据字段 key 列表，引用 data_fields.json |
| `input_fields_optional` | array[string] | 必填（可空数组） | 可选输入数据字段 key 列表 |
| `output_fields` | array[string] | ✅ | 模型输出字段 key 列表 |
| `performance_metrics` | object | ✅ | 模型性能指标，包含 auc/precision/recall/f1/ks 等 |
| `applicable_conditions` | string | ✅ | 适用条件/业务边界描述 |
| `unsuitable_conditions` | string | ✅ | 慎用/不适用场景描述 |
| `compliance_boundary` | string | ✅ | 合规边界说明 |
| `deployment_status` | string | ✅ | 部署状态：`production` / `staging` / `mock_available` / `development` |
| `api_available` | boolean | ✅ | 是否可通过 API 调用 |
| `historical_cases` | array[object] | ✅ | 历史落地案例列表，每个案例含 `client` / `description` / `effect` |
| `tags` | array[string] | ✅ | 标签 key 列表，引用 tags.json |
| `description` | string | ✅ | 模型详细描述 |
| `canonical_name` | string | 可选 | 标准模型名称；官方目录模型通常与 `model_name` 一致 |
| `aliases` | array[string] | 可选 | 模型别名，用于搜索、导入和名称对齐 |
| `source` | string | 可选 | 模型资产来源：`demo` / `official` / `imported` / `model_market` |
| `asset_version` | string | 可选 | 模型资产元数据版本，Repository 默认补 `1.0.0` |
| `asset_status` | string | 可选 | 资产状态，默认继承 `deployment_status` |
| `permission_scope` | string | 可选 | 权限范围，如 `demo_desensitized`、`official_catalog_internal` |
| `legal_boundary` | string | 可选 | 法律边界，默认继承 `compliance_boundary` |
| `input_schema` | object | 可选 | 结构化输入 schema；缺失时由必需输入字段自动生成基础 schema |
| `output_schema` | object | 可选 | 结构化输出 schema；缺失时由输出字段自动生成基础 schema |
| `result_schema` | object | 可选 | 模型调用结果 schema；缺失时由 `output_schema` 自动生成基础 schema |
| `total_questions` | number | 可选 | 官方评估数据中关联该模型的问题数，仅官方目录模型使用 |

---

## 3. 枚举值限定

### 3.1 domain（业务领域）

| 枚举值 | 中文 | 数据文件前缀 |
|--------|------|-------------|
| `credit_risk` | 信贷风控 | RISK_ |
| `customer_marketing` | 客户营销 | MKT_ |
| `operation_management` | 运营管理 | OPS_ |

### 3.2 business_stage（业务环节）

| 枚举值 | 中文 |
|--------|------|
| `pre_loan` | 贷前 |
| `in_loan` | 贷中 |
| `post_loan` | 贷后 |
| `pre_marketing` | 营销前 |
| `in_marketing` | 营销中 |
| `post_marketing` | 营销后 |
| `daily_operation` | 日常运营 |
| `risk_management` | 风险管理 |
| `compliance` | 合规管理 |
| `resource_planning` | 资源规划 |
| `performance_analysis` | 绩效分析 |

### 3.3 deployment_status（部署状态）

| 枚举值 | 说明 |
|--------|------|
| `production` | 已生产部署，可实时调用 |
| `staging` | 灰度/预发布环境 |
| `mock_available` | 可 Mock 调用，返回仿真结果 |
| `development` | 开发中，尚不可用 |

---

## 4. 完整样例

```json
{
  "model_id": "RISK_001",
  "model_name": "农户小额贷款准入评分模型",
  "domain": "credit_risk",
  "business_scenario": ["农户小额贷款贷前准入"],
  "business_stage": ["pre_loan"],
  "customer_segment": ["farmer", "rural_area"],
  "model_capability": ["admission_scoring", "credit_rating"],
  "input_fields_required": ["customer_profile", "loan_application"],
  "input_fields_optional": ["credit_report"],
  "output_fields": ["risk_score", "risk_level", "admission_decision"],
  "performance_metrics": {
    "auc": 0.82,
    "ks": 0.38,
    "precision": 0.78,
    "recall": 0.81
  },
  "applicable_conditions": "适用于农户经营性小额贷款（10万元以下）的贷前准入评分；要求申请人年龄在18-65周岁之间；适用于有稳定农业经营收入来源的客户。",
  "unsuitable_conditions": "不适用于无稳定收入来源的纯信用贷款；不适用于企业大额贷款（100万元以上）；不适用于非农业生产经营贷款场景。",
  "compliance_boundary": "评分结果仅作为授信参考，不构成最终审批决定；模型涉及客户个人信息处理需符合《个人信息保护法》；评分结果保留期限不超过贷款存续期+5年。",
  "deployment_status": "mock_available",
  "api_available": true,
  "historical_cases": [
    {
      "client": "XX农商银行",
      "description": "应用于农户小额贷款线上审批流程，日均处理申请300+笔。",
      "effect": "审批效率提升60%，不良率控制在1.2%以内。"
    }
  ],
  "tags": [
    "credit_risk", "pre_loan", "farmer", "rural_area",
    "admission_scoring", "small_loan", "agricultural"
  ],
  "description": "基于客户基本信息、经营数据和征信记录的准入评分模型，采用逻辑回归+特征交叉方法，对农户小额贷款申请进行自动化评分和分级。"
}
```

---

## 5. Repository 归一化规则

运行态模型资产统一通过 `ModelAssetRepository` 暴露。Repository 会在不修改源文件的前提下补齐以下字段：

- `asset_version`：缺失时为 `1.0.0`。
- `asset_status`：缺失时继承 `deployment_status`，仍缺失时为 `cataloged`。
- `permission_scope`：`official` 默认 `official_catalog_internal`，`demo` 默认 `demo_desensitized`。
- `legal_boundary`：缺失时继承 `compliance_boundary`。
- `input_schema`：由 `input_fields_required` 自动生成基础 object schema。
- `output_schema`：由 `output_fields` 自动生成基础 object schema。
- `result_schema`：由 `output_schema.properties` 自动生成基础结果 schema。
- 官方稀疏目录中缺失 `business_stage` 时，按业务域补默认阶段：风控为 `risk_management`，营销为 `pre_marketing`，运营为 `daily_operation`。

模型详情接口 `GET /api/v1/models/{model_id}` 返回的是 Repository 归一化后的资产详情，前端模型详情面板会展示输入 schema、输出 schema、权限范围、法律/合规边界和适用/不适用条件。

---

## 5. 数据存储说明

- **模型元数据**：存储为单文件或多文件均可，推荐每模型一文件便于管理
- **文件命名**：`data/knowledge/{model_id}.json`
- **标签体系**：`data/knowledge/tags.json`
- **数据字段字典**：`data/knowledge/data_fields.json`
- **组合模板**：`data/knowledge/composition_templates.json`
- **业务需求样本**：`data/samples/demand_samples.jsonl`
- **需求-模型标注**：`data/samples/demand_model_labels.jsonl`
- **组合场景样本**：`data/samples/composition_cases.jsonl`
- **评估数据**：`data/eval/intent_eval.jsonl`、`data/eval/tag_eval.jsonl`、`data/eval/topk_eval.jsonl`、`data/eval/explanation_survey_mock.json (survey) + explanation_eval.jsonl (test queries)`

---

## 6. 与 Agent A API Schema 的对齐

模型详情接口 `GET /api/v1/models/{model_id}` 响应中的 `model` 对象应包含本 Schema 定义的所有字段。Agent A 应直接引用本 Schema 定义 `ModelDetail` 结构。
