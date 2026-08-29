# 评估方法文档 (Evaluation Method)

## 1. 评估总览

本评估体系覆盖 Agent C 的四大核心能力：

| 能力 | 对应服务 | 评估指标 |
|------|----------|----------|
| 自然语言理解 | demand_parser.py | 意图准确率、标签 P/R/F1 |
| 模型推荐 | recommender.py | Top-K命中率、各维度评分分布 |
| 组合编排 | composition_planner.py | 组合评分、IO兼容率 |
| 整体流程 | 全链路 | 端到端Demo路径验证 |

## 2. 运行方式

```bash
# 轻量模式基础依赖
pip install -r backend/requirements-lock.txt

# 本地 CPU 稠密运行时（推荐直接使用下方 competition_dense 容器）
pip install -r backend/requirements-embeddings-lock.txt

# 官方主指标：默认关闭 LLM 和定向关键词，开启混合检索
python scripts/run_official_eval.py --all

# 按官方拆分评估
python scripts/run_official_eval.py --topk --split val
python scripts/run_official_eval.py --topk --split test

# 真实 LLM 重排；未配置真实 LLM 时直接失败
python scripts/run_official_eval.py --topk --split test --llm-mode on --llm-scope rerank --require-live-llm

# BGE-M3 独立消融；必须检查报告中的稠密覆盖率
python scripts/run_official_eval.py --topk --split val --llm-mode off --keyword-rules off --hybrid-retrieval on --dense-retrieval on --dense-weight 0.30 --output reports/official/eval_official_val_bge_m3_w030_results.json

# 可复现竞赛容器：固定模型 revision、离线权重、SHA-256 与 1024 维门禁
docker compose -f docker-compose.yml -f docker-compose.dense.yml --profile prepare run --rm dense-model-prepare
docker compose -f docker-compose.yml -f docker-compose.dense.yml up -d

# 运行单项评估
python scripts/run_eval.py --intent
python scripts/run_eval.py --tag
python scripts/run_eval.py --topk
python scripts/run_eval.py --composition
```

只有健康接口 `dense_available=true`、`dense_manifest_verified=true`、`dense_embedding_dimension=1024`，且报告 `dense_available_case_count` 等于样本数，才能宣称 BGE-M3 真实参与。`competition_dense` 任一稠密条件失败时直接拒绝推荐；轻量模式的稀疏结果不得替代正式指标。独立盲测使用 `scripts/blind_eval.py` 完成题目/答案分离、人工声明、近重复检查和冻结哈希校验，协议见 `docs/eval/blind_evaluation_protocol.md`。

## 3. 评估指标详解

### 3.1 意图识别准确率 (Intent Accuracy)

**定义**: 正确识别的需求意图占总测试用例的比例。

**公式**:
```
intent_accuracy = correct_predictions / total_cases × 100%
```

**测试用例**: `intent_eval` 数据集，包含 5 条标准需求+ 外部加载数据。

**判定标准**: 预测意图与标注意图完全一致。

### 3.2 标签提取 (Tag Precision/Recall/F1)

**定义**: 评估提取标签与标准标签集合的匹配程度。

**归一化**: 评估前，gold 标签和 predicted 标签均经 `normalize_eval_tag()` 统一转换为标准 tag key 后比对：
```
normalize_eval_tag(t):
  1. 若 t ∈ key_to_name → 返回 t（已是标准 key）
  2. 若 t ∈ name_to_key → 返回 name_to_key[t]（中文名→key）
  3. 否则 → 返回 t 原值
```

**公式**:
```
precision(单条) = |predicted ∩ gold| / |predicted|
recall(单条) = |predicted ∩ gold| / |gold|
f1(单条) = 2 × p × r / (p + r)
avg_precision = Σ precision / N
avg_recall = Σ recall / N
avg_f1 = Σ f1 / N
```

**输出**: details 中同时包含 `gold_tags`/`predicted_tags`（key 格式）和 `gold_tag_names`/`predicted_tag_names`（中文名格式），便于人工审查。

### 3.3 Top-K 命中率 (Top-K Hit Rate)

**定义**: 推荐结果 Top-K 中是否包含至少一个有效目标模型。

**parse_dict 字段**: 评估时将解析结果的 10 个字段传入推荐引擎（修复后补全了 4 个）：
```
intent, tags, business_scenario, customer_segment,
business_stage, expected_outputs,
data_conditions, product_type, risk_type, constraints
```

**公式**:
```
top3_hit_rate = count(top3 含 gold) / total_cases × 100%
top5_hit_rate = count(top5 含 gold) / total_cases × 100%
```

**说明**: 一个需求可能有多个等效的可用模型，只要命中其中一个即算命中。

**失败样本输出**: 评估完成后自动生成 `reports/examples/topk_failures.json`，包含所有 Top5 未命中的样本及其解析详情（query、parsed_intent、parsed_tags、parsed_scenario、parsed_customers、parsed_outputs 等），用于诊断推荐失败原因。

**调试字段**: details 中包含完整的解析结果快照（parsed_intent/parsed_tags/parsed_scenario/parsed_customers/parsed_outputs/parsed_data_conditions/parsed_product_type/parsed_risk_type），便于定位是解析问题还是推荐问题。

**混合检索口径**：默认使用事实模型知识卡字符 n-gram TF-IDF 与结构化通用评分融合。`use_keyword_rules=False` 时不执行模型名称定向 pair rules；`use_hybrid_retrieval=True` 时推荐结果包含 `hybrid_retrieval_match`。

**LLM 证据口径**：报告必须同时给出 `llm_available`、重排尝试/成功数、trace 样本覆盖率和唯一 trace 数。“请求开启 LLM”但没有 trace 的运行不得称为真实 LLM 评估。

### 3.4 组合适配度 (Composition Fit Score)

**定义**: 组合方案的七维综合评分。

**评判标准**:
- 60-100: 良好组合，覆盖完整流程
- 30-60: 基础组合，有提升空间
- 0-30: 降级方案或单模型兜底

### 3.5 可解释性 (Explanation Comprehensibility)

**定义**: 对 business / technical / management 三类解释文本，分别评估其对目标受众的可理解程度。

**公式**:
```
overall_comprehensibility = count(score >= 4) / total_cases * 100%
```

**测试样本**:
- `data/eval/explanation_eval.jsonl` — 10 条测试查询，驱动引擎生成三类解释，作为 LLM-judge 评分输入
- `data/eval/explanation_survey_mock.json` — 开发占位合成数据，非真人问卷，不作为达标证据；可解释性开发评估以 `reports/llm_judge/llm_judge_results.json` 的 LLM-as-Judge 实跑结果为准，真人问卷需使用 `docs/eval/standardized_questionnaire.md` 模板另行采集

**判定标准**:
- 每次查询生成 business / technical / management 三类解释
- LLM 按受众视角分别打分 1-5，分数 >= 4 视为可理解
- 指标名: `explanation_comprehensibility`，目标值 >= 90%

**输出结果**: 写入 `reports/examples/eval_results.json` 的 `explanation_evaluation` 节点，包含各模式平均分、可理解率和样本明细。

## 4. 评估数据集

### 4.1 内置数据集

Agent C 的 `data_loader.py` 内置 15 个模型的完整数据和 5 条标准评估样本。

### 4.2 外部数据集

当 Agent B 的数据就绪后，评估将自动使用更大的外部数据集：

| 数据类型 | 数据量 | 存储位置 |
|----------|--------|----------|
| 需求样本 | 30+ | `backend/data/demand_samples.json` |
| 模型数据 | 100+ | `backend/data/exported_models/` |
| 评估用例 | 20+ | `backend/data/eval_sets/` |
| 组合模板 | 5+ | `backend/data/compositions/` |

## 5. 评估结果输出

### 5.1 控制台输出

```
============================================================
Model Market Assistant - Evaluation Suite
============================================================

>>> Intent Evaluation...
  Accuracy: 94.5% (104/110)

>>> Tag Extraction Evaluation...
  Precision: 0.9213
  Recall: 0.8871
  F1: 0.9039

>>> Top-K Evaluation...
  Top3 Hit Rate: 93.3%
  Top5 Hit Rate: 93.3%

>>> Composition Evaluation...
  Avg Score: 80.1

>>> Explanation Evaluation...
  Overall Comprehensibility: 100.0%

============================================================
SUMMARY
============================================================
  Intent Accuracy: 94.5%
  Tag F1: 0.9039
  Top3 Hit Rate: 93.3%
  Top5 Hit Rate: 93.3%
  Composition Avg Score: 80.1
  Explanation Comprehensibility: 100.0%

============================================================
```

### 5.2 JSON 结果文件

评估结果自动保存为 `reports/examples/eval_results.json`，包含详细的逐条数据。

## 6. 单元测试

对每个服务模块有单独的单元测试：

```bash
cd backend
python -m pytest tests/test_parse.py -v
python -m pytest tests/test_recommend.py -v
python -m pytest tests/test_composition.py -v
python -m pytest tests/ -v  # 全部测试
```

### 测试覆盖范围

| 测试文件 | 测试类 | 测试用例数 |
|----------|--------|-----------|
| test_parse.py | TestIntentIdentification | 10 |
| test_parse.py | TestSlotExtraction | 5 |
| test_parse.py | TestTagNormalization | 4 |
| test_parse.py | TestClarification | 4 |
| test_recommend.py | TestModelRecall | 4 |
| test_recommend.py | TestScoring | 3 |
| test_recommend.py | TestEvidenceAndGaps | 4 |
| test_recommend.py | TestTopK | 2 |
| test_recommend.py | TestDemoPaths | 3 |
| test_composition.py | TestTemplateMatching | 3 |
| test_composition.py | TestIOCompatibility | 2 |
| test_composition.py | TestCompositionScore | 2 |
| test_composition.py | TestFallback | 1 |
| test_composition.py | TestUsageGuide | 1 |

## 7. 验收标准

| 验收项 | 最低标准 | 目标标准 |
|--------|----------|----------|
| 意图识别准确率 | ≥60% | ≥80% |
| 标签提取 F1 | ≥0.5 | ≥0.7 |
| Top3 命中率 | ≥50% | ≥80% |
| Top5 命中率 | ≥60% | ≥90% |
| 组合适配度 | ≥30 | ≥60 |
| 单元测试通过率 | 100% | 100% |
| 端到端Demo路径 (3条) | 全部通过 | 全部通过 |
