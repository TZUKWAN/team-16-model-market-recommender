# 算法方法文档 (Algorithm Method)

> **文档状态：历史设计稿。** 本页保留用于追溯早期规则方案，其中的权重、候选集规模和置信度公式不代表当前实现。当前算法、实际公式与数据审计结论请以 [`../technical/KEY_ALGORITHMS_AND_FORMULAS.md`](../technical/KEY_ALGORITHMS_AND_FORMULAS.md) 为准（自 2026-07-22 起，算法说明唯一正式交付物为该 Markdown 文件，公式使用 LaTeX，不再生成对应 Word 文档）。

## 1. 自然语言解析算法 (Demand Parser)

### 1.1 意图识别 (Intent Identification)

**方法**: 基于规则的关键词匹配 (Rule-based Keyword Matching)

**算法流程**:
1. 对输入文本进行分词（按空格/标点/中文语义单元分割）
2. 将分词结果与三个领域的关键词库进行匹配：
   - **客户营销 (customer_marketing)**: 营销,推广,转化,新客,获客,流失,响应,名单
   - **信贷风控 (credit_risk)**: 风控,风险,欺诈,贷前,贷后,逾期,评分,准入,额度
   - **运营管理 (operation_management)**: 运营,网点,客流,渠道,降本,增效
3. 统计各域的匹配数量，选择匹配数最多的域作为意图
4. 置信度 = 最高匹配数 / 总匹配数（带平滑处理）

**公式**:
```
intent = argmax_domain count(matches_domain)
confidence = max_count / max(total_count, 1) * min(max_count / 3, 1.0)
```

### 1.2 槽位提取 (Slot Extraction)

| 槽位 | 提取方式 | 关键词示例 |
|------|----------|-----------|
| customer_segment | 匹配客户群体模式 | 农户,县域,小微,对公,新客 |
| product_type | 匹配产品类型模式 | 首贷,小额贷款,经营贷 |
| business_stage | 匹配业务阶段模式 | 贷前,贷中,贷后 |
| business_scenario | 组合识别 | 场景描述提取 |
| expected_outputs | 匹配输出需求模式 | 名单,评分,预警,报告 |
| data_requirements | 匹配数据需求模式 | 需要数据,关联,外部数据 |

### 1.3 标签标准化 (Tag Normalization)

系统采用 **tag key / tag_names 双字段设计**，确保后端内部比对使用标准 key，前端展示使用中文名：

- `tags`: 标准 tag key 列表（如 `credit_risk`, `farmer`, `anti_fraud`）
- `tag_names`: 中文展示名列表（如 `信贷风控`, `农户`, `反欺诈`）
- `tag_confidence`: 以 tag key 为键的置信度字典

**三级查找 `_to_tag_key(value)`**：将任意输入（口语化表达、中文名、key）统一映射为标准 key：

```
1. 若 value ∈ valid_tag_keys → 直接返回（已是标准 key）
2. 若 value ∈ synonym_map → 返回 synonym_map[value]（同义词→key）
3. 遍历 tag_key_to_name，若 value == 中文名 → 返回对应 key
4. 以上均不匹配 → 返回 None（丢弃，不放入 tags）
```

**`_tag_names(tag_keys)`**：将 key 列表映射为中文名列表，供前端展示。

**`_normalize_tags()`** 规则版标签提取流程：
1. 从 customer_segment / product_type / risk_type / expected_outputs 中提取标签 key（经 `_to_tag_key` 归一化）
2. 从 intent 生成 domain 标签
3. 从关键词匹配生成 capability 标签（admission_scoring / anti_fraud / default_prediction 等）
4. 所有标签经 `valid_tag_keys` 校验，非法 key 自动丢弃
5. 按置信度降序排列

| 口语化表达 | 标准 key | 中文名 |
|------------|----------|--------|
| 能不能贷,能不能批 | admission_scoring | 准入评分 |
| 会不会坏账,坏账,不良 | default_prediction | 违约预测 |
| 转化,容易买,响应 | conversion_prediction | 转化预测 |
| 是不是骗贷,虚假 | anti_fraud | 反欺诈 |
| 评分,打分 | admission_scoring | 准入评分 |
| 跑路,失联 | early_warning | 预警监测 |

### 1.4 标签推断 (Tag Enrichment)

`_enrich_tags()` 在标签提取后，基于上下文线索**推断额外标签**，覆盖长尾场景。所有推断均经 `valid_tag_keys` 校验，不存在的 key 自动跳过。

**6 类推断规则：**

| 类别 | 触发关键词 | 推断标签 key |
|------|-----------|-------------|
| **Domain** | 始终 | `add_tag(intent)` |
| **Stage** | 贷前/贷中/贷后/营销/日常运营/绩效/资源/合规 | `pre_loan` / `in_loan` / `post_loan` / `pre_marketing` / `in_marketing` / `daily_operation` / `performance_analysis` / `resource_planning` / `compliance` |
| **Customer** | 农户/县域/小微/对公/个人/存量/沉睡/流失/新客 | `farmer` / `rural_area` / `county_new_customer` / `small_micro_enterprise` / `corporate` / `individual` / `existing_customer` / `dormant_customer` / `churned_customer` / `new_customer` |
| **Product** | 小额/涉农/对公贷款/消费贷/信用卡/存款/首贷 | `small_loan` / `agricultural_loan` / `corporate_loan` / `consumer_loan` / `credit_card` / `deposit` / `first_loan` |
| **Capability** | 反欺诈/准入/额度/逾期/预警/异常/反洗钱/合规/流失/响应/转化/名单/需求/绩效/资源/偏好/价值 | `anti_fraud` / `admission_scoring` / `amount_calculation` / `default_prediction` / `early_warning` / `anomaly_detection` / `anti_money_laundering` / `compliance_check` / `churn_prediction` / `response_prediction` / `conversion_prediction` / `priority_ranking` / `demand_forecasting` / `performance_analysis` / `resource_optimization` / `preference_analysis` / `value_assessment` |
| **Compliance** | 合规/监管/制度/报表 | `compliance_check` / `compliance` |

**长尾场景覆盖示例：**

| 输入 | 推断标签 |
|------|---------|
| 反洗钱可疑交易监测 | `anti_money_laundering` + `compliance_check` + `anomaly_detection` + `anti_fraud` |
| 网点客流预测和智能排班 | `resource_optimization` + `resource_planning` + `daily_operation` |
| 客户流失预警与挽留 | `churn_prediction` + `churned_customer` + `existing_customer` |

### 1.5 缺失槽位检测与澄清

当关键槽位缺失时，自动生成澄清问题。
- 缺失客户群体 → "请问您关注哪类客户群体？(农户/县域/小微/对公)"
- 缺失业务场景 → "请问您的业务场景是什么？(营销/风控/运营)"
- 缺失业务阶段 → "您需要贷前、贷中还是贷后的模型？"

---

## 2. 模型推荐算法 (Model Recommender)

### 2.1 多阶段召回 (Multi-Stage Recall)

采用漏斗式过滤 + 语义扩展，逐层缩小候选集：

```
全量模型 (105)
  → 领域匹配 (domain filter, +3分)
  → 场景匹配 (scenario filter, +3分)
  → 标签匹配 (tag overlap, 经 _normalize_tag_to_key 归一化, +1.5分/标签)
  → 客户群体匹配 (customer segment filter, +2分)
  → 输出匹配 (output type filter, +2分)
  → 能力匹配 (capability filter, 经 _normalize_tag_to_key 归一化, +2.5分)
  → 语义重叠 (semantic overlap, _token_overlap_score > 0.08, +score×4分)
  → 候选不足5个时放宽过滤
  → Top-K 排序
```

**语义召回**：构建 query_text（场景+标签+客群+输出+产品+风险）与 model_text（名称+描述+场景+标签+能力+输出+适用条件），通过 `_token_overlap_score` 计算关键词重叠率。阈值 > 0.08 时加分。

### 2.2 七维加权评分 (7-Dimension Weighted Scoring)

**公式**:
```
total_score = (scenario_match × 0.25) +
              (customer_match × 0.15) +
              (data_match × 0.20) +
              (output_match × 0.15) +
              (performance × 0.10) +
              (landing_experience × 0.10) +
              (compliance × 0.05)
```

各维度评分方法:

| 维度 | 权重 | 计算方法 |
|------|------|----------|
| scenario_match | 0.25 | 基于Jaccard相似度的业务场景匹配度 |
| customer_match | 0.15 | 客户群体与模型目标客户的匹配程度 |
| data_match | 0.20 | 需求输入数据字段与模型输入字段的覆盖率 |
| output_match | 0.15 | 期望输出与模型输出的匹配程度 |
| performance | 0.10 | 模型性能指标标准化评分 (AUC/准确率) |
| landing_experience | 0.10 | 基于历史部署经验的评分 |
| compliance | 0.05 | 合规性检查通过率 |

### 2.3 语义匹配 (Semantic Matching)

使用基于集合的关键词重叠（非向量化，无需外部依赖）：

**`_tokenize_text(text)`**：将文本分词为 token 集合：
1. 替换标点分隔符为空格
2. 按空格分割 + 按 `_` 分割子词
3. 对预定义 35 个银行关键词（反洗钱、可疑交易、合规、网点、客流、排班、流失、欺诈等）做子串匹配

**`_token_overlap_score(query_text, model_text)`**：
```
score = |tokens(query) ∩ tokens(model)| / max(|tokens(query)|, 1)
```

**Jaccard 相似度**（用于场景匹配）：
```
Jaccard(tags, model_tags) = |tags ∩ model_tags| / |tags ∪ model_tags|
```

### 2.4 评分标准化 (Score Normalization)

将各维度原始分映射到 [0, 1] 区间：
- **百分制指标**: / 100
- **计数指标**: min(count / target, 1.0)
- **存在性指标**: 0 或 1

### 2.5 标签归一化比对 (Tag Comparison Normalization)

`_normalize_tag_to_key(tag)` 在推荐引擎中统一标签比对口径：

```
1. 若 tag ∈ synonym_map → 返回 synonym_map[tag]（中文名/同义词→key）
2. 否则 → 返回 tag 原值（已是 key）
```

**应用场景：**

| 比对场景 | 方法 |
|---------|------|
| Tag overlap | `query_tags` 和 `model_tags` 均经 `_normalize_tag_to_key().lower()` 归一化后求交集 |
| Capability match | `tag_caps` 和 `model_cap` 均经归一化后求交集，命中加 2.5 分 |
| Output match 回退 | expected_outputs 精确匹配失败后，用 `tag_set` vs `model_caps_set`（cap_overlap）和 `tag_set` vs `model_tags_set`（tag_overlap）回退评分 |

**Output match 回退公式：**
```
cap_overlap > 0 → min(90, 60 + cap_overlap × 10)
tag_overlap > 0 → min(85, 55 + tag_overlap × 8)
```

### 2.6 LLM 语义重排 (LLM Semantic Reranking)

当 LLM 可用时，对 Top-20 候选模型进行语义重排：

**候选信息传递**：每个候选模型向 LLM 传递 7 个字段：
```
ID - name
  domain: 领域
  scenarios: 业务场景列表
  capabilities: 模型能力列表
  tags: 标签列表
  outputs: 输出字段列表
  description: 模型描述
  applicable: 适用条件
```

**System prompt 策略**：
- 按 semantic relevance、tag match、output match、business applicability、domain fit 排序
- **保留跨域模型**：当需求明确需要合规、运营、营销或风控支持时，不丢弃跨域候选
- 输出格式：`{"ranked": ["ID1", "ID2", ...]}`

**用户需求传递**：包含 requirement、intent、tags、customers、outputs 五个维度。

---

## 3. 组合编排算法 (Composition Planner)

### 3.1 模板匹配 (Template Matching)

预定义业务流程模板，根据需求标签自动匹配：

| 模板ID | 流程节点 | 适用场景 |
|--------|----------|----------|
| LOAN_APPROVAL | 反欺诈 → 准入评分 → 额度预估 → 贷后预警 | 信贷全流程 |
| CUSTOMER_MARKETING | 客群筛选 → 转化预测 → 响应预测 | 精准营销 |
| RISK_MONITORING | 风险识别 → 贷后预警 → 处置建议 | 风险监控 |

### 3.2 模型-节点分配 (Model-to-Node Assignment)

为模板中的每个节点分配最优模型：

1. 遍历候选模型
2. 计算模型能力与节点能力的匹配度 (capability_eq)
3. 选择匹配度最高的模型

**节点适配度**:
```
node_fit_score = capability_match × 0.6 + jaccard_tag_match × 0.4
```

### 3.3 IO兼容性检查 (IO Compatibility Check)

检查连接节点之间的输入输出兼容性：

| 维度 | 要求 |
|------|------|
| 输出-输入字段覆盖 | 前节点输出字段覆盖后节点输入字段的比例 |
| 数据类型兼容 | 字段类型一对一匹配 |
| 数据格式一致 | 明确或隐含格式匹配 |

### 3.4 七维组合评分

```
composition_score = (process_coverage × 0.25) +
                    (scenario_consistency × 0.20) +
                    (node_fit_avg × 0.20) +
                    (io_compatibility × 0.15) +
                    (data_availability × 0.10) +
                    (landing_feasibility × 0.05) +
                    (compliance_feasibility × 0.05)
```

### 3.5 降级策略 (Fallback)

当无模板匹配时：
1. 尝试使用默认模板（通用流程）
2. 若仍不匹配，退回单模型推荐模式
3. 将单模型结果包装为单节点编排方案

---

## 4. 解释生成算法 (Explanation Generator)

### 4.1 三层输出模式

| 模式 | 受众 | 内容特点 |
|------|------|----------|
| 业务版 (business) | 业务人员 | 业务价值、应用场景、历史效果 |
| 技术版 (technical) | 数据科学家 | 模型类型、性能指标、技术细节 |
| 管理版 (management) | 管理层 | 投入产出、风险提示、合规评估 |

### 4.2 证据卡生成

基于历史部署案例生成证据卡片，每条证据包含：
- 案例名称
- 效果指标（如 ROI、准确率提升）
- 适用客户类型
- 风险提示

---

## 5. 数据与外部依赖

- **无外部 LLM 依赖**: 所有算法基于规则 + 集合运算
- **内置降级数据**: data_loader.py 内置 15 个模型的完整数据（fallback）
- **外部数据**: Agent B 数据就绪后自动优先加载外部 JSON 文件（105 个模型、88 个标签）
- **可选 LLM 增强**: 当 LLM_API_KEY 配置时，需求解析和语义重排使用 LLM；无 Key 时自动降级为规则版
