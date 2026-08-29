# Official Evaluation Leakage & Overfitting Audit
**Generated:** 2026-06-30T21:31:45.379218

## 1. Audit Summary

| Audit Item | Result | Risk Level | Notes |
|------------|--------|------------|-------|
| 1. Metadata Generation Source | model_list_only | low | Model metadata derived from model list only; no query/answer text used. |
| 2. Query-Text Leakage in Metadata | no_substantial_leakage | low | Found 56 overlaps; all are generic business phrases. |
| 3. Gold Answer Access in Recommender | no_access | low | Recommender signature takes query+top_k only; never reads gold answers. |
| 4. Hardcoded Rules | no_suspicious_rules | low | Found 0 patterns; none are genuine leakage. |
| 5. Masked Model-Name Sanity Check | evaluated | medium | Val top1=53.1%; Test top1=54.8% |
| 6. Name+Description-Only Sanity Check | evaluated | medium | Val top1=82.8%; Test top1=87.1% |
| 7. Train/Val/Test Similarity | moderate_similarity | medium | Val avg sim=0.1821; Test avg sim=0.1763 |

## 2. Current Official Metrics

| Metric | Val | Test |
|--------|----:|-----:|
| Total Queries | 64 | 62 |
| Top1 Rate | 82.8% | 87.1% |
| Top3 Rate | 96.9% | 95.2% |
| Top5 Rate | 100.0% | 96.8% |

## 3. Leakage Checks

### 3.1 Metadata Generation Source

- **Result:** model_list_only
- **Risk Level:** low
- **Evidence:** Metadata fields (model_name, description, domain, business_scenario, tags) are derived solely from the 模型清单_参考 Excel sheet. Domain/business_scenario/tags are inferred heuristically from model_name+description (see prepare_official_dataset.py lines 256-344). No val/test/train query text or gold answer fields are used.

### 3.2 Query-Text Leakage in Metadata

- **Result:** no_substantial_leakage
- **Risk Level:** low
- **Total Overlaps Found:** 56
- **Evidence:** Searched all val/test query Chinese substrings (length>=8) across all model metadata fields (model_name, description, business_scenario, tags). Found 56 overlaps; most are generic business phrases that naturally co-occur in banking context. No evidence of query-specific phrases injected into model metadata.

**Top Overlap Examples:**

| # | Query ID | Split | Model ID | Field | Matched Text |
|---|----------|-------|----------|-------|-------------|
| 1 | test_0011 | test | OFFICIAL_047 | description | `有征信记录的信用` |
| 2 | test_0011 | test | OFFICIAL_047 | description | `记录的信用卡申请` |
| 3 | test_0011 | test | OFFICIAL_047 | description | `征信记录的信用卡` |
| 4 | test_0011 | test | OFFICIAL_047 | description | `信记录的信用卡申` |
| 5 | test_0011 | test | OFFICIAL_048 | description | `记录的信用卡申请` |
| 6 | test_0011 | test | OFFICIAL_048 | description | `征信记录的信用卡` |
| 7 | test_0011 | test | OFFICIAL_048 | description | `信记录的信用卡申` |
| 8 | test_0024 | test | OFFICIAL_030 | description | `日前办理分期的概` |
| 9 | test_0024 | test | OFFICIAL_030 | description | `款日前办理分期的` |
| 10 | test_0024 | test | OFFICIAL_030 | description | `前办理分期的概率` |
| 11 | test_0024 | test | OFFICIAL_030 | description | `当月账单消费余额` |
| 12 | test_0024 | test | OFFICIAL_030 | description | `还款日前办理分期` |
| 13 | test_0024 | test | OFFICIAL_030 | description | `在还款日前办理分` |
| 14 | test_0024 | test | OFFICIAL_030 | tags | `当月账单消费余额` |
| 15 | test_0035 | test | OFFICIAL_007 | description | `针对小微企业构建` |
| 16 | test_0040 | test | OFFICIAL_022 | description | `银行体系贷款客户流失压力较大` |
| 17 | test_0040 | test | OFFICIAL_022 | description | `客户流失压力较大` |
| 18 | test_0040 | test | OFFICIAL_022 | description | `体系贷款客户流失` |
| 19 | test_0040 | test | OFFICIAL_022 | description | `贷款客户流失压力` |
| 20 | test_0040 | test | OFFICIAL_022 | description | `行体系贷款客户流` |

### 3.3 Gold Answer Access in Recommender

- **Result:** no_access
- **Risk Level:** low
- **Recommender accesses gold:** False
- **Evaluator passes gold to recommender:** False
- **recommend() signature:** `recommend(self, query, top_k=5)`
- **Evidence:** OfficialRecommender.recommend() signature takes only query and top_k. It never reads gold_model_ids, gold_model_names, or any answer/label fields. evaluate_official_topk.py passes query text only to recommend() and uses gold answers only after receiving recommendations to compute hit rates.

### 3.4 Hardcoded Rules

- **Result:** no_suspicious_rules
- **Risk Level:** low
- **Suspicious Patterns Found:** 0
- No suspicious hardcoded query-to-model mappings found.
- **Evidence:** Scanned 4 files for hardcoded query-model rules, OFFICIAL_XX conditionals, and per-query phrase matches. Found 0 potentially suspicious patterns (after filtering acceptable OFFICIAL_ prefix validation in recommender.__init__ and dataset ID prefix checks). None represent genuine leakage.

### 3.5 Masked Model-Name Sanity Check

- **Result:** evaluated
- **Risk Level:** medium
- Masked Val: Top1=53.1% Top3=68.8% Top5=71.9% (N=64)
- Masked Test: Top1=54.8% Top3=72.6% Top5=80.6% (N=62)

### 3.6 Name+Description-Only Sanity Check

- **Result:** evaluated
- **Risk Level:** medium
- NameDesc Val: Top1=82.8% Top3=96.9% Top5=100.0% (N=64)
- NameDesc Test: Top1=87.1% Top3=95.2% Top5=96.8% (N=62)

### 3.7 Train/Val/Test Similarity

- **Result:** moderate_similarity
- **Risk Level:** medium
- **Val avg max similarity:** 0.1821
- **Test avg max similarity:** 0.1763
- **High similarity count (val):** 0
- **High similarity count (test):** 0
- **Threshold:** 0.6
- **Evidence:** Computed Jaccard similarity (character bigrams) between each val/test query and all train queries sharing the same gold_model_id. Moderate similarity is expected since queries for the same model revolve around the same business scenario. High similarity cases may indicate limited expression diversity between train and val/test splits.

## 4. Sanity Check Results

| Condition | Val Top1 | Val Top3 | Val Top5 | Test Top1 | Test Top3 | Test Top5 |
|-----------|---------|---------|---------|----------|----------|----------|
| Original | 82.8% | 96.9% | 100.0% | 87.1% | 95.2% | 96.8% |
| Masked Model-Name | 53.1% | 68.8% | 71.9% | 54.8% | 72.6% | 80.6% |
| Name+Description Only | 82.8% | 96.9% | 100.0% | 87.1% | 95.2% | 96.8% |

**Drop vs Original (percentage points):**

| Drop | Val Top1 | Val Top3 | Val Top5 | Test Top1 | Test Top3 | Test Top5 |
|------|---------|---------|---------|----------|----------|----------|
| Masked Drop | -29.7pp | -28.1pp | -28.1pp | -32.3pp | -22.6pp | -16.2pp |
| NameDesc Drop | +0.0pp | +0.0pp | +0.0pp | +0.0pp | +0.0pp | +0.0pp |

## 5. Similarity Analysis

- **Val avg max similarity (Jaccard, char bigrams):** 0.1821
- **Test avg max similarity:** 0.1763
- **High similarity (>0.6) count:** Val=0, Test=0

High similarity indicates that train, val, and test queries for the same model use similar language — this is expected for business-domain data but introduces mild overfitting risk.

## 6. Final Judgement

**Overall Risk Level:** medium

### Conclusion

未发现 recommender 直接读取 gold_model_ids/gold_model_names。
未发现针对 test/val query_id 的硬编码规则。
official_60 推荐指标主要来自模型名称、描述、标签与 query 的关键词/语义匹配。
仍存在轻度到中度过拟合风险，因为官方数据每个模型的 train/val/test 问题围绕同一业务模型，表达存在相似性。
Top3/Top5 指标可作为 official 数据集推荐效果，但不宜夸大为复杂开放域泛化能力。
建议后续补充：遮蔽模型名评测、人工标注标签评测、更多跨表达测试样本。

### Recommendations

1. Run masked model-name evaluation regularly to track name-overreliance.
2. Add human-annotated tag-only evaluation to test semantic matching.
3. Expand test set with more diverse paraphrases of the same business need.
4. Consider adding a cross-validation split to reduce train/val similarity.

---
_Report generated by `scripts/audit_official_leakage.py` at 2026-06-30T21:31:45.379218_