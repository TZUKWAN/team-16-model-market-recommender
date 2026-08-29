# 主数据集接入契约文档

## 1. 概述

本文档定义银行模型市场智能推荐助手的 **主数据集接入契约**。所有数据集的目录结构、字段规范、质量规则和接入流程均须遵循本契约约束。新增或扩展数据时，应优先参考本契约和各数据 Schema 文档。

**声明：所有数据均为模拟/脱敏样例数据，不包含任何真实客户、交易或银行信息。**

---

## 2. 主数据集目录建议

建议将数据按类型分目录存放，保持清晰的文件组织：

| 目录 | 用途 | 文件格式 | 备注 |
|------|------|----------|------|
| `data/knowledge/` | 模型知识库，每个模型一个 JSON 文件 | `.json` | 模型元数据、标签体系、字段字典、组合模板 |
| `data/samples/` | 需求样本与标注 | `.jsonl` | 业务需求、模型标注、组合场景 |
| `data/eval/` | 评测集 | `.jsonl` | 意图/标签/TopK/解释满意度评估 |

新增数据时应放置到对应目录，不要混放。具体文件清单详见 `docs/data/dataset_card.md`。

---

## 3. 模型知识库必填字段

每个模型元数据文件（`data/knowledge/{model_id}.json`）必须包含以下必填字段，详见 `docs/data/knowledge_schema.md`：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `model_id` | string | 唯一，格式：`{RISK|MKT|OPS}_XXX`（3位数字） | 模型唯一标识 |
| `model_name` | string | 非空 | 模型中文名称，体现业务含义 |
| `domain` | string | 枚举值：`credit_risk` / `customer_marketing` / `operation_management` | 业务领域 |
| `business_scenario` | array[string] | 非空数组 | 业务场景描述列表 |
| `business_stage` | array[string] | 非空数组，值须在标签体系中存在 | 业务环节标签 |
| `customer_segment` | array[string] | 非空数组，值须在标签体系中存在 | 目标客群标签 |
| `model_capability` | array[string] | 非空数组，值须在标签体系中存在 | 模型能力标签 |
| `input_fields_required` | array[string] | 非空数组 | 必填输入数据字段 key，引用 data_fields.json |
| `output_fields` | array[string] | 非空数组 | 模型输出字段 key |
| `tags` | array[string] | 非空数组，所有值须在 tags.json 中存在 | 标签 key 列表 |
| `description` | string | 非空 | 模型详细描述 |

### 模型 ID 前缀约定

| 前缀 | 领域 | 示例 |
|------|------|------|
| `RISK_` | `credit_risk`（信贷风控） | `RISK_001` |
| `MKT_` | `customer_marketing`（客户营销） | `MKT_001` |
| `OPS_` | `operation_management`（运营管理） | `OPS_001` |

---

## 4. 需求评测集建议字段

评测文件 `data/eval/intent_eval.jsonl`（意图评估）建议包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `test_id` | string | 是 | 测试用例唯一标识 |
| `query` 或 `raw_text` | string | 是 | 用户原始需求文本 |
| `expected_intent` 或 `intent` | string | 是 | 期望的意图分类 |
| `expected_tags` 或 `tags` | array[string] | 否 | 期望的标签列表 |
| `gold_model_ids` 或 `gold_ids` | array[string] | 否 | 期望关联的模型 ID 列表 |
| `expected_domain` | string | 否 | 期望的业务领域 |
| `difficulty` | string | 否 | 难度等级：`easy` / `medium` / `hard` |

### 字段映射说明

实际字段名可根据已有数据文件保持一致。例如 `intent_eval.jsonl` 当前使用 `expected_intent` 和 `expected_domain`，而 `tag_eval.jsonl` 使用 `expected_tags`。保持各文件内部的字段一致性即可。

---

## 5. 组合评测集建议字段

组合场景评测文件 `data/samples/composition_cases.jsonl` 建议包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `case_id` | string | 是 | 场景唯一标识 |
| `raw_text` 或 `description` | string | 是 | 组合场景描述文本 |
| `expected_models` 或 `models` | array[string] | 是 | 期望涉及的模型 ID 列表 |
| `expected_flow` 或 `stages` | array[object] | 否 | 期望的业务流程阶段 |
| `expected_domain` | string | 否 | 期望的业务领域 |
| `complexity` | string | 否 | 复杂度：`high` / `medium` / `low` |

### 组合流程阶段结构（stages）

当使用 `stages` 字段时，每个阶段建议包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `stage_order` | integer | 阶段序号 |
| `stage_name` | string | 阶段名称 |
| `model_id` | string | 该阶段推荐的模型 ID |

---

## 6. 数据质量规则

所有入库数据必须满足以下质量规则。验证脚本 `scripts/validate_data.py` 会自动执行这些检查。

### 6.1 模型元数据规则

| 规则 | 说明 | 违规处理 |
|------|------|---------|
| model_id 唯一性 | 知识库中 model_id 不可重复 | 阻止入库 |
| 必填字段非空 | 第 3 节所列必填字段不可为空或 null | 阻止入库 |
| 列表字段类型 | `business_scenario`、`business_stage` 等列表字段必须为数组，不可混用逗号字符串 | 阻止入库 |
| domain 限定 | `domain` 必须在 `credit_risk`、`customer_marketing`、`operation_management` 三者之中 | 阻止入库 |
| model_id 格式 | model_id 必须匹配 `{RISK|MKT|OPS}_XXX` 格式 | 阻止入库 |
| tags 引用完整性 | `tags` 数组中所有值必须在 `tags.json` 中存在 | 阻止入库 |
| input_fields 引用完整性 | `input_fields_required` 中所有值必须在 `data_fields.json` 中存在 | 阻止入库 |

### 6.2 评测集规则

| 规则 | 说明 | 违规处理 |
|------|------|---------|
| gold_model_ids 引用完整 | `gold_model_ids`（或 `expected_model_ids`）中的所有 model_id 必须在知识库中存在 | 阻止入库 |
| query 非空 | `query` 或 `raw_text` 不可为空 | 阻止入库 |
| 难度有效 | `difficulty` 值必须为 `easy`、`medium` 或 `hard`（如存在） | 警告 |

### 6.3 通用规则

| 规则 | 说明 | 违规处理 |
|------|------|---------|
| JSON/JSONL 格式合法 | 所有数据文件必须为合法的 JSON 或 JSONL 格式 | 阻止入库 |
| UTF-8 编码 | 所有数据文件必须使用 UTF-8 编码 | 阻止入库 |
| 字段命名风格 | 字段名使用 snake_case（小写+下划线） | 建议 |

---

## 7. 主数据集接入流程

新增或更新数据集时，请按以下步骤操作：

### 步骤 1：放入数据到对应目录

将数据文件放入 `data/knowledge/`、`data/samples/` 或 `data/eval/` 目录，保持文件命名风格与已有数据一致。

- 模型知识库：`data/knowledge/{model_id}.json`
- 需求样本：`data/samples/demand_samples.jsonl`
- 评估数据：`data/eval/intent_eval.jsonl` 等

### 步骤 2：运行数据校验

```bash
python scripts/validate_data.py
```

校验脚本检查所有数据文件的 schema 合规性、引用完整性和格式正确性。输出结果应显示 **ALL CHECKS PASSED**，否则需要根据错误提示修正数据。

### 步骤 3：运行全量评估

```bash
python scripts/run_eval.py --all
```

该命令对所有评估集执行推荐性能评估，生成评测指标。若测试数据新增，需确保已添加对应的评测用例到 `data/eval/` 下。

### 步骤 4：失败归因分析

```bash
python scripts/analyze_eval_failures.py
```

分析评估中的失败案例，输出分类归因结果。该步骤帮助理解数据质量问题或模型匹配短板，避免盲目调参。

### 步骤 5：查看评测快照

评测结果快照存储在 `reports/runs/` 目录下，包含每次评估的时间戳、指标摘要和失败案例详情。推荐在每次数据变更后对比快照变化：

```bash
ls reports/runs/
```

### 接入流程图

```text
[数据放入目录] --> [validate_data.py 校验]
    |                        |
    | 失败 <--- 修正数据 ---  |
    |                        |
    v                       v (通过)
[run_eval.py 评估] --> [analyze_eval_failures.py 归因]
                              |
                              v
                     [reports/runs/ 查看快照]
```

---

## 8. 附加说明

### 8.1 当前数据状态

当前数据集（105 个模型、105 条需求样本、3 个领域）为 **smoke / baseline 测试数据**，主要用于：

- 验证数据接入流程是否正常
- 验证推荐引擎的基础功能
- 验证评估管线的可用性

**不建议针对当前小数据集过拟合调参**，因为样本量有限且均为模拟数据。待真实或更大规模的数据集接入后，再基于评测结果进行系统性优化。

### 8.2 参考文档

- `docs/data/knowledge_schema.md` — 模型元数据字段结构详细定义
- `docs/data/tag_taxonomy.md` — 标签体系分类和使用规范
- `docs/data/dataset_card.md` — 数据集汇总说明
- `docs/eval/evaluation_method.md` — 评估方法说明
- `scripts/validate_data.py` — 数据校验脚本（源码）
- `scripts/run_eval.py` — 评估执行脚本（源码）

### 8.3 扩展建议

- 新增领域时，更新 `tags.json` 中的 `domain_tags` 并同步更新本契约的 domain 枚举
- 新增模型时，确保 `tags` 和 `input_fields_required` 引用已在标签体系和字段字典中注册
- 新增评测类型时，在 `data/eval/` 下添加文件并更新 `scripts/validate_data.py` 的校验规则

---

*最后更新：2026-06-29*
