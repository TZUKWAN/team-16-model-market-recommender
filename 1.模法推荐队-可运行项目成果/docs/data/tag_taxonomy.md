# 标签体系说明

## 1. 概述

本文档定义模型市场智能推荐助手中的标准化标签体系。标签用于：

1. **模型元数据标注**：为每个模型打上多维度标签，支持检索和推荐
2. **需求意图解析**：将用户自然语言需求解析为标准标签
3. **需求-模型匹配**：通过标签匹配实现模型推荐

**⚠ 声明：所有标签均为模拟/样例设计，用于演示推荐系统能力。**

---

## 2. 标签分类结构

标签分为 **8 大类别**，每类下有若干具体标签：

```
标签体系
├── 1️⃣ 业务领域标签（domain_tags）       → 3 个
├── 2️⃣ 业务环节标签（business_stage_tags） → 11 个
├── 3️⃣ 客群标签（customer_segment_tags）   → 15 个
├── 4️⃣ 产品标签（product_tags）            → 11 个
├── 5️⃣ 模型能力标签（capability_tags）     → 20 个
├── 6️⃣ 输出结果标签（output_tags）         → 10 个
├── 7️⃣ 数据要求标签（data_requirement_tags）→ 10 个
└── 8️⃣ 合规边界标签（compliance_tags）      → 8 个
```

**标签总数：88 个**

---

## 3. 标签 JSON 结构

每个标签包含以下字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | ✅ | 标签唯一标识，英文小写+下划线 |
| `name` | string | ✅ | 标签中文名称 |
| `synonyms` | array[string] | ✅ | 同义词/近义词列表，用于需求解析时的标签映射 |
| `description` | string | ✅ | 标签详细含义说明 |

### 示例

```json
{
  "key": "anti_fraud",
  "name": "反欺诈",
  "synonyms": ["欺诈识别", "欺诈检测", "欺诈评分"],
  "description": "识别和防范欺诈行为的模型能力"
}
```

---

## 4. 标签分类详解

### 4.1 业务领域标签

| key | 名称 | 用途 |
|-----|------|------|
| `credit_risk` | 信贷风控 | 贷前中后全流程风控模型 |
| `customer_marketing` | 客户营销 | 客户获取转化留存模型 |
| `operation_management` | 运营管理 | 网点运营和流程优化模型 |

### 4.2 业务环节标签

| key | 名称 | 适用领域 |
|-----|------|---------|
| `pre_loan` | 贷前 | 信贷风控 |
| `in_loan` | 贷中 | 信贷风控 |
| `post_loan` | 贷后 | 信贷风控 |
| `pre_marketing` | 营销前 | 客户营销 |
| `in_marketing` | 营销中 | 客户营销 |
| `post_marketing` | 营销后 | 客户营销 |
| `daily_operation` | 日常运营 | 运营管理 |
| `risk_management` | 风险管理 | 运营管理 |
| `compliance` | 合规管理 | 运营管理 |
| `resource_planning` | 资源规划 | 运营管理 |
| `performance_analysis` | 绩效分析 | 运营管理 |

### 4.3 客群标签（部分示例）

完整列表见 `data/knowledge/tags.json`。

| key | 名称 | 典型场景 |
|-----|------|---------|
| `farmer` | 农户 | 涉农贷款、农业金融 |
| `small_micro_enterprise` | 小微企业和个体工商户 | 普惠金融 |
| `corporate` | 对公客户/企业 | 对公业务 |
| `new_customer` | 新客 | 新客获取 |
| `dormant_customer` | 沉睡客户 | 客户唤醒 |

### 4.4 模型能力标签

| key | 名称 | 典型输出 |
|-----|------|---------|
| `admission_scoring` | 准入评分 | 准入分数/等级 |
| `anti_fraud` | 反欺诈 | 欺诈评分/标记 |
| `default_prediction` | 违约预测 | 违约概率 |
| `early_warning` | 预警监控 | 预警信号 |
| `conversion_prediction` | 转化预测 | 转化概率 |
| `churn_prediction` | 流失预测 | 流失概率 |
| `cross_selling` | 交叉销售 | 产品推荐列表 |

### 4.5 合规边界标签

| key | 名称 | 说明 |
|-----|------|------|
| `personal_info_protection` | 个人信息保护合规 | 符合《个人信息保护法》 |
| `fair_lending` | 公平信贷合规 | 确保无歧视性结果 |
| `model_audit` | 模型可审计 | 决策过程可追溯 |
| `anti_money_laundering` | 反洗钱合规 | 符合反洗钱法规 |

---

## 5. 标签使用规范

### 5.1 模型标注

每个模型元数据的 `tags` 数组应包含对应维度的标签 key：
```json
{
  "tags": ["credit_risk", "pre_loan", "farmer", "admission_scoring", ...]
}
```

### 5.2 需求标注

每条需求样本的 `gold_tags` 数组包含解析后标签：
```json
{
  "gold_tags": ["credit_risk", "pre_loan", "farmer", "admission_scoring"]
}
```

### 5.3 标签匹配规则

推荐系统进行标签匹配时遵循以下规则：
1. **精确匹配**：需求标签与模型 tags 有交集即视为匹配
2. **同义词扩展**：通过标签的 synonyms 进行语义扩展
3. **层级继承**：业务领域标签作为最上层分类
4. **组合优先**：同时匹配多个维度标签的模型优先推荐

---

## 6. 数据文件位置

- 标签数据（JSON）：`data/knowledge/tags.json`
- 标签说明文档：`docs/data/tag_taxonomy.md`
