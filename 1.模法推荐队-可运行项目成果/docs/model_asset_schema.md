# 模型资产 Schema

本文档描述 `ModelAssetRepository` 暴露给推荐、详情、组合和后续知识图谱模块的统一模型资产字段。

## 核心身份字段

- `model_id`：模型唯一 ID，例如 `MKT_001`、`OFFICIAL_001`。
- `model_name`：模型展示名称。
- `canonical_name`：标准名称；官方目录模型通常与 `model_name` 一致。
- `aliases`：别名列表，用于导入和检索。
- `source`：资产来源，当前支持 `demo`、`official`，未来可扩展为 `imported`、`model_market`。
- `asset_version`：资产元数据版本，默认 `1.0.0`。
- `asset_status`：资产状态，优先继承 `deployment_status`。

## 业务适配字段

- `domain`：业务域，如 `credit_risk`、`customer_marketing`、`operation_management`。
- `business_scenario`：适用业务场景列表。
- `business_stage`：业务阶段列表。
- `customer_segment`：适用客群列表。
- `model_capability`：模型能力标签列表。
- `tags`：综合标签列表。
- `description`：模型说明。

## 输入输出字段

- `input_fields_required`：必需输入字段。
- `input_fields_optional`：可选输入字段。
- `output_fields`：输出字段。
- `input_schema`：由输入字段生成或导入的结构化输入 schema。
- `output_schema`：由输出字段生成或导入的结构化输出 schema。
- `result_schema`：模型调用结果 schema，默认基于 `output_schema` 生成。

## 治理字段

- `permission_scope`：权限范围。`official` 默认 `official_catalog_internal`，`demo` 默认 `demo_desensitized`。
- `legal_boundary`：法律/合规边界，默认继承 `compliance_boundary`。
- `compliance_boundary`：模型使用合规说明。
- `applicable_conditions`：适用条件。
- `unsuitable_conditions`：不适用条件。
- `api_available`：是否已有可调用 API。
- `historical_cases`：落地案例说明列表。
- `performance_metrics`：性能指标字典。

## Repository 保证

`ModelAssetRepository` 在加载时会：

- 合并现有 105 个 demo 模型与官方 60 个模型。
- 补齐 `asset_version`、`asset_status`、`permission_scope`、`legal_boundary`。
- 将输入、输出字段归一化为列表。
- 自动生成基础 `input_schema`、`output_schema`、`result_schema`。
- 检查重复 `model_id` 和关键字段缺失。

当前健康接口 `/api/v1/health` 会返回：

- `model_asset_repository_ready`
- `model_asset_total`
- `model_asset_by_source`
- `model_asset_by_domain`
- `model_asset_validation_issues`
