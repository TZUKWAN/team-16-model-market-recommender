# 数据集说明文档 (Dataset Card)

## 概述

本文档说明模型市场智能推荐助手中使用的所有数据集。仓库包含竞赛官方模型目录与官方问题数据，也包含模拟、合成、鲁棒扰动和脱敏演示数据；不包含真实客户明细、真实交易流水、生产银行凭据或生产模型调用结果。

模拟数据的生成方法、数量、随机种子和使用边界统一见 [`synthetic_dataset_card.md`](synthetic_dataset_card.md)。数据完整性与过拟合风险以 [`../../reports/audit/data_integrity_audit_20260722.md`](../../reports/audit/data_integrity_audit_20260722.md) 为准；其中由规则自动派生且标记为 `needs_review=true` 的意图/标签属于弱标签，不应表述为官方人工真值。

## 官方数据集

本项目已接入官方竞赛数据集，同时保留早期 demo 数据作为 baseline。数据按 `source` 字段分为三类：official、demo、extended。

### 文件清单

| 文件 | 路径 | 记录数 | 说明 |
|------|------|--------|------|
| `official-v1` 权威模型顺序 | `data/official_60/models.jsonl` | 60 | 官方模型稳定 ID 的权威顺序 |
| ID 映射表 | `data/official_60/official_id_mapping.json` | 60 | `feature-v1` 到 `official-v1` 的迁移映射 |
| 官方模型目录 | `data/official/model_catalog_structured.jsonl` | 60 | 官方模型元数据 |
| 官方模型原始目录 | `data/official/model_catalog_raw.jsonl` | 60 | 原始模型清单 |
| 名称映射表 | `data/official/model_name_map.json` | 60 | 规范名称 ↔ OFFICIAL_xxx 映射 |
| 问题全集 | `data/official/questions_all.jsonl` | 417 | 全部问题（train+val+test） |
| 训练集 | `data/official/questions_train.jsonl` | 291 | 训练样本 |
| 验证集 | `data/official/questions_val.jsonl` | 64 | 验证样本 |
| 测试集 | `data/official/questions_test.jsonl` | 62 | 测试样本 |
| 意图评估 | `data/eval_official/intent_eval_official.jsonl` | 417 | 官方意图评估 |
| 标签评估 | `data/eval_official/tag_eval_official.jsonl` | 417 | 官方标签评估 |
| TopK 评估 | `data/eval_official/topk_eval_official.jsonl` | 417 | 官方 TopK 评估 |
| 组合评估 | `data/eval_official/combo_eval_official_manual.jsonl` | 10 | 手动构造组合评估 |

### Schema（模型目录）

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_id` | string | 稳定 ID，格式 `OFFICIAL_xxx` |
| `canonical_name` | string | 模型规范名称 |
| `aliases` | list | 别名列表（当前为空） |
| `domain` | string | 领域：`credit_risk` / `customer_marketing` / `operation_management` |
| `description` | string | 模型描述（目标用户、正样本、用途） |
| `source` | string | 固定为 `official` |
| `total_questions` | int | 该模型对应问题数 |

### Schema（问题）

| 字段 | 类型 | 说明 |
|------|------|------|
| `question_id` | string | 问题 ID，如 `train_0001` |
| `user_query` | string | 自然语言查询 |
| `gold_model_id` | string | 标准模型 ID |
| `gold_model_name` | string | 标准模型名称 |
| `split` | string | 划分：`train` / `val` / `test` |
| `intent_primary` | string | 主意图 |
| `intent_domain` | string | 意图领域 |
| `intent_task` | string | 意图任务 |
| `expected_tags` | list | 预期标签 |
| `source` | string | 固定为 `official` |
| `annotation_version` | string | 标注版本 |
| `needs_review` | bool | 是否需要人工复核 |

### 数据重合说明

- **demo 模型与官方模型名称精确重合为 0**（`scripts/convert_official_dataset.py` 已验证）。
- 官方数据使用 `OFFICIAL_xxx` 稳定 ID，与 demo 数据的 `RISK_xxx` / `MKT_xxx` / `OPS_xxx` 完全隔离。
- 默认单模型推荐以 `official-v1` 为主榜，并把 `demo-v1` 候选放入独立的 `demo_references` 参考区；二者不混排。官方评估、推荐版本与组合推荐仍只使用官方结果，且官方目录缺失时不回退 Demo。
- `feature-v1` 到 `official-v1` 的 60 项映射中有 57 个 ID 发生变化，21,924 处引用已迁移；迁移统计与覆盖校验见 `reports/data_governance/official_id_migration_report.json`。

## 数据集汇总

| 数据集 | 文件 | 规模 | 用途 |
|--------|------|------|------|
| 模型元数据 | `data/knowledge/{model_id}.json` | 105 个模型 | 模型知识库基础数据 |
| 标签体系 | `data/knowledge/tags.json` | 88 个标签，8 大类别 | 模型分类和检索 |
| 数据字段字典 | `data/knowledge/data_fields.json` | 44 个字段 | 定义模型输入输出字段 |
| 组合模板 | `data/knowledge/composition_templates.json` | 6 个模板 | 标准化的模型组合模板 |
| 业务需求样本 | `data/samples/demand_samples.jsonl` | 105 条 | NLU 意图识别训练/评估 |
| 需求-模型标注 | `data/samples/demand_model_labels.jsonl` | 127 条 | 推荐相关性标注 |
| 组合场景样本 | `data/samples/composition_cases.jsonl` | 35 条 | 组合推荐场景 |
| 意图评估 | `data/eval/intent_eval.jsonl` | 50 条 | 意图分类评估 |
| 标签评估 | `data/eval/tag_eval.jsonl` | 20 条 | 标签推荐评估 |
| TopK 评估 | `data/eval/topk_eval.jsonl` | 15 条 | 模型推荐排序评估 |
| 解释满意度调研 | `data/eval/explanation_survey_mock.json (survey) + explanation_eval.jsonl (test queries)` | 1 份模拟报告 | 推荐解释评估 |

---

## 1. 模型元数据

**存储位置**：`data/knowledge/{model_id}.json`

**规模**：105 个模型，覆盖 3 大业务领域

| 领域 | 前缀 | 数量 | 典型场景 |
|------|------|------|----------|
| 信贷风控 | RISK_ | 35 | 准入评分、反欺诈、违约预测、贷后预警 |
| 客户营销 | MKT_ | 35 | 新客转化、交叉销售、流失预警、精准营销 |
| 运营管理 | OPS_ | 35 | 网点运营、反洗钱、合规管理、流程优化 |

**字段结构**：共 19 个字段，详见 `docs/data/knowledge_schema.md`

**数据来源**：全部为模拟构造，基于公开的银行业务实践经验设计，不涉及任何真实银行数据。

---

## 2. 标签体系

**存储位置**：`data/knowledge/tags.json`

**规模**：88 个标签，8 大类别

| 类别 | 标签数量 | 说明 |
|------|----------|------|
| domain_tags | 3 | 业务领域标签 |
| business_stage_tags | 11 | 业务环节标签 |
| customer_segment_tags | 15 | 目标客群标签 |
| product_tags | 11 | 产品类型标签 |
| capability_tags | 20 | 模型能力标签 |
| output_tags | 10 | 输出类型标签 |
| data_requirement_tags | 10 | 数据需求标签 |
| compliance_tags | 8 | 合规要求标签 |

每个标签包含 key（英文标识）、name（中文名称）、synonyms（同义词列表）和 description（说明）。

---

## 3. 数据字段字典

**存储位置**：`data/knowledge/data_fields.json`

**规模**：44 个字段，覆盖 12 类银行数据

**分类**：
- 客户基础信息（客户画像、联系方式、地址等）
- 征信数据（征信报告、信用历史、逾期记录等）
- 交易数据（交易流水、收支情况、交易分类等）
- 资产负债信息（资产信息、负债信息、净资产等）
- 信贷申请数据（贷款申请、贷款用途、抵押物信息等）
- 营销数据（营销触达记录、活动响应、渠道偏好等）
- 渠道行为数据（APP行为、线上活动、网点访问等）
- 企业经营数据（经营收入、现金流、税务信息等）
- 网点运营数据（柜面业务、排队数据、ATM使用等）
- 担保信息（担保信息）
- 供应链数据（供应链数据）
- 员工数据（员工工作负荷等）

每个字段包含 field_key、name、category、sensitivity（敏感度等级）和 mock_note（脱敏说明）。

---

## 4. 业务需求样本

**存储位置**：`data/samples/demand_samples.jsonl`

**规模**：105 条需求样本

**字段**：
- `demand_id`: 需求唯一标识（DEMAND_001 ~ DEMAND_105）
- `user_query`: 自然语言业务需求描述
- `intent`: 意图分类标签
- `scenario`: 业务场景中文描述
- `urgency`: 紧急程度（high/medium/low）

**分布**：
- 信贷风控需求：35 条（DEMAND_001 ~ DEMAND_035）
- 客户营销需求：35 条（DEMAND_036 ~ DEMAND_070）
- 运营管理需求：35 条（DEMAND_071 ~ DEMAND_105）

---

## 5. 需求-模型标注

**存储位置**：`data/samples/demand_model_labels.jsonl`

**规模**：127 条标注

**字段**：
- `demand_id`: 需求标识
- `model_id`: 模型标识
- `relevance_score`: 相关性评分（0.0 ~ 1.0）
- `label_type`: 标注类型（primary/alternative）
- `annotator`: 标注者标识（expert_1 ~ expert_6）
- `note`: 标注说明

**分布**：
- primary 标注：105 条（每个需求对应一个最相关模型）
- alternative 标注：22 条（补充相关模型）

---

## 6. 组合场景样本

**存储位置**：`data/samples/composition_cases.jsonl`

**规模**：35 条组合场景

**字段**：
- `case_id`: 场景标识（COMP_001 ~ COMP_035）
- `name`: 场景名称
- `description`: 场景描述
- `models`: 涉及的模型 ID 列表
- `demand_ids`: 关联的需求 ID 列表
- `scenario`: 业务场景分类
- `complexity`: 复杂度（high/medium/low）
- `estimated_impact`: 预期效果

**覆盖**：
- 纯信贷风控场景：9 个（COMP_001 ~ COMP_009）
- 纯客户营销场景：7 个（COMP_010 ~ COMP_016）
- 纯运营管理场景：10 个（COMP_017 ~ COMP_026）
- 跨域综合场景：9 个（COMP_027 ~ COMP_035）

---

## 7. 组合模板

**存储位置**：`data/knowledge/composition_templates.json`

**规模**：6 个标准化模板

| 模板 ID | 名称 | 阶段数 | 复杂度 |
|---------|------|--------|--------|
| TMPL_001 | 信贷全流程风控模板 | 3 | high |
| TMPL_002 | 精准营销全链路模板 | 3 | medium |
| TMPL_003 | 网点运营优化模板 | 3 | medium |
| TMPL_004 | 反洗钱合规管理模板 | 2 | high |
| TMPL_005 | 客户全生命周期经营模板 | 3 | high |
| TMPL_006 | 人力资源管理数字化模板 | 3 | medium |

---

## 8. 评估数据

### 8.1 意图评估
- **文件**：`data/eval/intent_eval.jsonl`
- **规模**：50 条测试用例
- **字段**：test_id, query, expected_intent, expected_domain, difficulty
- **难度分布**：easy 20 条，medium 24 条，hard 6 条

### 8.2 标签评估
- **文件**：`data/eval/tag_eval.jsonl`
- **规模**：20 条测试用例
- **字段**：test_id, query, expected_tags, difficulty

### 8.3 TopK 推荐评估
- **文件**：`data/eval/topk_eval.jsonl`
- **规模**：15 条测试用例
- **字段**：test_id, query, expected_model_ids, k, scenario

### 8.4 解释满意度调研
- **文件**：`data/eval/explanation_survey_mock.json (survey) + explanation_eval.jsonl (test queries)`
- **内容**：模拟 50 名业务用户的满意度调研，含 Likert 5 点量表评分和开放式反馈

---

## 9. 数据质量说明

| 指标 | 数值 |
|------|------|
| 模型总数 | 105（demo）/ 60（official） |
| 需求样本数 | 105（demo）/ 417（official） |
| 标注总数 | 127（demo） |
| 组合场景数 | 35（demo）/ 10（official） |
| 组合模板数 | 6 |
| 标签覆盖率 | 模型 tags 字段引用均来自 tags.json |
| 数据字段引用完整性 | 模型 input_fields 引用均在 data_fields.json 中 |
| schema 合规率 | 100%（验证脚本通过） |
| 官方数据重合度 | demo 与 official 模型名称精确重合为 0 |

## 10. 数据使用说明

1. **数据加载**：使用 `scripts/load_data.py` 中的函数加载各数据集
2. **数据验证**：运行 `python scripts/validate_data.py` 验证数据完整性
3. **数据边界**：官方模型目录与官方问题来自竞赛数据；demo、synthetic、robustness 和调用结果分别按来源标注。所有数据均不包含真实客户明细、真实交易流水或生产银行凭据
4. **扩展性**：新增模型时只需在 `data/knowledge/` 下添加对应的 JSON 文件
5. **编码**：所有数据文件使用 UTF-8 编码
6. **`source` 字段区分**：所有数据记录均包含 `source` 字段，用于区分数据来源：
   - `official` — 官方竞赛数据
   - `demo` — 早期模拟数据
   - `extended` — 后续扩展数据（预留）

---

*最后更新：2026-07-15*
*数据版本：v1.2*

---

## 迁移说明

从 v1.0（仅 demo 数据）迁移到 v1.2（official + demo 隔离目录）时，请注意：

1. **模型 ID 隔离**：官方模型使用 `OFFICIAL_xxx` 前缀，demo 模型使用 `RISK_xxx` / `MKT_xxx` / `OPS_xxx` 前缀，二者互不冲突。
2. **权威顺序**：`data/official_60/models.jsonl` 的 60 行顺序决定 `official-v1` ID；不要再按 `feature-v1` 顺序生成 ID。
3. **旧 ID 迁移**：外部缓存、数据库或报告若保存过 `feature-v1` ID，必须使用 `data/official_60/official_id_mapping.json` 映射。重新映射会改变 57 个模型的 ID，但不改变模型名称和官方描述。
4. **数据加载**：`data/official/model_catalog_structured.jsonl` 是运行时官方资产目录；转换和重映射分别由 `scripts/convert_official_dataset.py` 与 `scripts/remap_official_ids.py` 管理。
5. **来源策略**：默认 `official_then_demo` 返回官方主榜和独立 Demo 参考区；Demo 不参与官方指标、版本榜单或组合推荐。显式 `official` / `demo` 可请求单一目录，禁止 mixed 和官方缺失时回退 Demo。
6. **评估隔离**：官方评估集位于 `data/eval_official/`，与 `data/eval/` 下的 demo 评估集独立运行；demo 数据仅作为 smoke test 和演示保留。
