# 模拟数据生成说明

版本：2026-07-22

适用项目：模型市场智能推荐助手

说明目的：只解释仓库中的模拟/合成数据是怎样生成的，以及它们能做什么、不能证明什么。

## 1. 总体说明

项目中的模拟数据不是从银行生产系统抽取，也不含真实客户明细、交易流水、身份信息、生产模型调用结果或真实银行验收报告。模拟数据分为四类：

1. 105 个 Demo 模型资产；
2. 官方 60 模型的本地补全草稿字段；
3. 基于官方问题生成的 3000 条规则合成问句；
4. 鲁棒扰动数据和 LLM 合成流程样例。

这四类数据的生成方法和用途不同，均不能冒充竞赛官方原始数据或真实银行生产数据。

## 2. 105 个 Demo 模型是怎样模拟的

### 2.1 设计方法

Demo 模型按三个业务域等量设计：

| 业务域 | ID 前缀 | 数量 |
|---|---|---:|
| 信贷风控 | `RISK_` | 35 |
| 客户营销 | `MKT_` | 35 |
| 运营管理 | `OPS_` | 35 |
| 合计 | — | 105 |

团队先依据竞赛题目覆盖的银行业务方向和一般业务常识，项目开发阶段在 JSONL 中预置/整理模型名称、适用场景和能力，再用结构化 JSON 模板补齐以下字段：

- 业务场景、业务阶段和目标客群；
- 模型能力、标签、必需/可选输入字段和输出字段；
- 适用条件、不适用条件和合规边界；
- 演示性性能指标、部署状态、接口状态和历史案例；
- 模型简介。

原始定义位于：

- `scripts/model_data/risk_models.jsonl`；
- `scripts/model_data/mkt_models.jsonl`；
- `scripts/model_data/ops_models.jsonl`。

`scripts/generate_models.py` 将三类 JSONL 逐条写入 `data/knowledge/{model_id}.json`。这一步只是格式转换，不会从外部系统抓取数据，也不会训练模型。

### 2.2 数值和案例如何构造

Demo 文件中的 AUC、KS、Precision、Recall、提升率、处理时长等数值，是为了让页面、排序、报告和组合编排能够完整演示而设置的合理化示例值，不是实测结果。

历史案例使用“XX银行”“XX农商行”等占位名称，效果描述也是演示文案。`deployment_status` 和 `api_available` 表示软件演示中的能力状态，不代表该模型真的已经在某家银行生产部署或存在真实接口。

因此，Demo 数据允许用于：

- 前后端功能演示；
- 模型详情、对比、收藏、反馈和组合编排测试；
- 用户显式选择 Demo 时的补充参考；
- 单元测试和接口联调。

Demo 数据不得用于证明模型真实准确率、真实业务收益或银行落地数量。

## 3. 官方 60 模型的补全草稿是怎样模拟的

竞赛官方数据直接提供模型名称、模型描述和问题—目标模型关系，但没有提供系统展示所需的全部结构化字段。

`scripts/enrich_official_models.py` 只使用模型 ID、官方名称、官方描述和领域，通过本地确定性规则补全：

- `customer_segment`：根据“农户、小微、对公、AUM、新客、沉睡、流失”等关键词推断；
- `performance_metrics`：按领域、模型序号和名称关键词生成演示性指标；
- `historical_cases`：按业务域套用“脱敏试点示例”模板。这里的脱敏只是模板文案，不代表存在真实原始案例。

生成过程不调用 LLM，也不访问外部服务。每条记录均标记：

```text
enrichment_method = deterministic_local_rules_no_external_llm
enrichment_review_status = draft_requires_manual_review
```

性能指标的具体构造方式包括：

- 信贷风控：以模型序号做确定性偏移，构造 AUC、KS；反欺诈类再补 Recall，额度/定价类再补 MAPE；
- 客户营销：构造 AUC、Top 10% Lift、Top 20% Precision 和 PSI 阈值；
- 运营管理：构造 Accuracy、Coverage；预测类补 MAPE，合规/风险类补 Recall。

这些值都带有“非生产验收值、需人工校验”的说明。仓库的字段来源报告将 `performance_metrics` 和 `historical_cases` 标为 `synthetic_draft`，核验数量为 0。

## 4. 3000 条规则合成问句是怎样生成的

### 4.1 输入和脚本

- 生成脚本：`scripts/generate_synthetic_official_data.py`；
- 模型输入：`data/official/model_catalog_structured.jsonl`；
- 问题输入：`data/official/questions_all.jsonl`；
- 随机种子：`20260706`；
- 目标数量：3000 条；
- 每个官方模型：50 条；
- 覆盖模型：60/60。

生成命令：

```powershell
python scripts\generate_synthetic_official_data.py --total 3000 --seed 20260706
```

### 4.2 生成步骤

对每个官方模型执行以下过程：

1. 从官方描述中用规则抽取“目标用户、正样本、用途”。
2. 聚合同一目标模型下官方问题的 `expected_tags` 和 `intent_task`，形成模型画像。
3. 生成多类问句模板，包括直接询问、目标导向、用途导向、正样本导向、角色需求、口语化表达、结果导向、边界询问和短问句。
4. 对少量官方种子问句做固定替换，例如“如何→怎么”“推荐哪个→应该选哪个”。
5. 随机加入业务前缀、补充限制、长上下文和少量错别字，形成 `easy`、`medium`、`hard`、`noisy` 四种难度。
6. 使用固定随机种子保证可复现，并按归一化问句 SHA-1 摘要去重。
7. 把目标模型 ID、名称、领域和标签作为继承标签写入记录。

输出文件：

- `data/synthetic/synthetic_questions_all.jsonl`；
- `data/synthetic/synthetic_questions_train.jsonl`；
- `data/synthetic/synthetic_questions_val.jsonl`；
- `data/synthetic/synthetic_questions_test.jsonl`；
- `data/eval_synthetic/*.jsonl`；
- `data/synthetic/synthetic_manifest.json`。

当前结果为：

| 项目 | 数量 |
|---|---:|
| 总量 | 3000 |
| train | 2100 |
| val | 450 |
| test | 450 |
| 唯一问句哈希 | 3000 |
| 空标签样本 | 0 |

难度分布为 easy 585、medium 1256、hard 811、noisy 348。

### 4.3 重要审计边界

当前生成器读取 `questions_all`，而其中包含官方 train、val、test。因此现有 3000 条数据虽然没有被当前运行时排序器读取，但不能直接作为新的训练/调参集，否则会把由 val/test 派生的信息重新带回训练链路。

若未来需要训练解析器或排序器，必须修改生成入口，只读取 `questions_train.jsonl`，重新生成一套 train-only 合成数据；官方 val 只用于模型选择，官方 test 或新外部盲测集只用于最终确认。

## 5. 鲁棒扰动数据是怎样生成的

`scripts/generate_robust_eval.py` 对每条官方问题生成五种确定性变体：

1. 同义词替换，如“如何→怎么”“客户→客群”；
2. 口语化前后缀；
3. 错别字或空格噪声；
4. 增加适用边界、输入数据、输出和合规要求的长上下文；
5. 混入次要领域信息，同时明确本次优先目标。

结果位于 `data/eval_robustness/robust_eval.jsonl`。目标模型和标签继承自源问题，所以它用于测试表达扰动下的稳定性，不是独立的新人工标注集。

## 6. LLM 合成数据是怎样生成的

`scripts/generate_synthetic_with_llm.py` 可以在安全注入 `LLM_PROVIDER`、`LLM_MODEL`、`LLM_BASE_URL` 和 `LLM_API_KEY` 后，让外部 LLM 按模型画像生成更自然的需求问句。生成后会做：

- 模型 ID 合法性检查；
- 解析领域一致性检查；
- 标签交集检查；
- 重复问句检查；
- 疑似个人信息检查；
- 人工抽检标记。

当前仓库只有 `data/synthetic_llm/synthetic_llm_dry_run_template.jsonl` 及其 manifest，没有正式 live LLM 合成结果。dry-run 仅验证字段、去重和文件输出，不能描述成已经调用真实 LLM 生成。

## 7. 系统现在怎样使用这些模拟数据

- 正式推荐默认只对官方 60 模型排序。
- 105 个 Demo 模型只在显式 Demo/参考区域出现，不与官方主榜混排。
- 当前运行时排序器不读取 3000 条合成问句。
- 官方模型补全的模拟性能指标和案例会进入内部结构化评分，因此可能对排序产生有限影响；页面已隐藏该内部推荐分，但数据来源风险仍需在正式表述中注明。
- BGE-M3 使用公开预训练权重做向量化；在当前仓库、已扫描代码路径及已检查制品中，未发现用上述模拟数据微调 BGE-M3 的代码、训练入口或训练制品；该结论不覆盖仓库外活动。


## 9. `needs_review` 与弱标签继承说明

3000 条规则合成问句当前均标记为 `needs_review=false`，但这只表示生成脚本未将其显式标为待复核，并不代表其标签已经过独立人工审核。

这些标签的继承方式如下：

- `intent_task` 与 `expected_tags` 来自源官方问题的弱标签，通过模板和规则继承到合成问句；
- 目标模型 ID、名称、领域和标签同样来自官方模型目录或生成模板；
- 难度字段（`easy`/`medium`/`hard`/`noisy`）和扰动由确定性规则注入。

如果未来重新生成该合成语料，建议：

- 将每条记录显式设为 `needs_review=true`；或
- 新增字段 `label_status=synthetic_inherited_unverified`，以表明标签来自合成继承且未经独立人工验证。

在缺少上述标记前，不得将 3000 条合成问句的标签作为独立人工标注或生产级训练标签使用。

## 10. `split` 字段缺失说明

`data/eval_synthetic/*.jsonl` 下的 3000 条合成数据（每个文件 3000 条）**没有 `split` 字段**。因此：

- 这些文件不能自然对应到 train/val/test 的独立划分；
- 只能将其整体视为一套“合成诊断集”，用于统一检查生成质量、格式一致性和下游脚本兼容性；
- 任何把它们描述为“合成 train 评测”“合成 val 评测”或“合成 test 评测”的说法都会混淆划分边界。

如果未来需要按 split 评估，必须在生成脚本中显式写入 `split` 字段，并保证每个 split 的来源与官方 train/val/test 严格一致。

## 11. 后处理与 ID 重映射

3000 条合成问句在生成后经历了官方 ID 重映射后处理：

- 60 个官方模型 ID 中有 57 个被重映射到新的统一 ID 空间；
- 2850 条合成问题的目标模型 ID 被替换为对应的新官方 ID；
- 1511 条困难负例的替换目标模型 ID 也同步完成重映射。

详细迁移记录见 `reports/data_governance/official_id_migration_report.json`。

该后处理改变了输出文件中的 ID 值，但保留了原始问题文本和标签继承关系。因此审计或复现时，必须把 ID 重映射视为合成制品血缘的一部分；否则会出现“同一问题对应两个不同 ID”的困惑。

## 12. `synthetic_manifest.json` 血缘缺失说明

当前 `data/synthetic/synthetic_manifest.json` 记录了生成总量、随机种子、覆盖模型数和输出文件列表，但缺少以下关键血缘信息：

- 输入文件 SHA-256（`questions_all.jsonl`、`model_catalog_structured.jsonl`）；
- 生成脚本自身的提交哈希或版本标识；
- 每条合成记录的父问题 ID 与父问题所在 split（train/val/test）的血缘；
- ID 重映射后的新旧 ID 对照记录。

此外，固定随机种子 `20260706` 只能保证在同一脚本版本、同一依赖版本和同一输入字节下得到可复现结果；它不能保证跨环境、跨提交或跨输入文件的“字节级”一致。因此，在缺少输入哈希和脚本版本的情况下，不得宣称当前合成制品可完全按种子逐字节复现。


## 13. 一句话对外说明

> 项目的模拟数据由团队围绕竞赛业务域设计的 105 个 Demo 模型、对官方模型描述进行本地规则补全的草稿字段，以及基于官方问句模板生成的合成与扰动问句组成；它们只用于软件演示、开发和稳健性测试，不含真实客户数据，也不作为真实银行生产效果证明。
