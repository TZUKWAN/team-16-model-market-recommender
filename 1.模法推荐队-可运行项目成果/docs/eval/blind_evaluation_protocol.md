# 独立盲测与防泄漏评估协议

## 目的

该流程用于证明推荐系统对未见业务需求的泛化能力。它不生成合成题目，也不把开发者自测包装成独立盲测。没有真实出题人和复核人的数据，只能作为开发测试，不能标记为正式证据。

## 角色隔离

1. 开发者先冻结代码、推荐配置和模型资产版本。
2. 出题人仅查看业务场景说明，不查看官方 417 条问题、关键词规则或推荐结果。
3. 复核人根据模型目录标注一个主模型及零个或多个等效可接受模型。
4. 开发者只拿到无答案题目；私有答案由评估负责人保管。
5. 冻结后使用 SHA-256 校验，任何修改都会使评估失败。

软件只能校验声明、ID分离、文件内容和哈希，不能证明两个ID背后一定是不同真人。因此工具生成的报告默认 `formal_blind_evidence=false`；最终正式证据必须另附真实人员名单、签字或可核验的评审记录，由评估负责人在答辩材料中人工确认。

## 公开题目格式

每行一个 JSON 对象，必须包含：`case_id`、`query`、`scenario`、`author_id`、`authorship_attestation`。其中 `authorship_attestation` 固定为 `independent_human_authored`。

公开文件不得包含任何 `gold_*`、`expected_model_ids`、`acceptable_model_ids` 或 `primary_model_id` 字段，也不得在问题中直接写模型 ID 或完整模型名称。

## 私有答案格式

每行包含：`case_id`、`primary_model_id`、`acceptable_model_ids`、`reviewer_id`、`review_status`、`review_attestation`。其中：

- `review_status` 必须为 `approved`。
- `review_attestation` 固定为 `independent_human_review`。
- `reviewer_id` 必须与对应题目的 `author_id` 不同。
- `acceptable_model_ids` 支持多个业务等效模型，减少单一弱标签误判。

私有答案必须使用 `*.private.jsonl` 命名，不提交到 Git。

## 执行流程

```powershell
python scripts\blind_eval.py validate --cases data\eval_blind\cases.jsonl --labels data\eval_blind\labels.private.jsonl --manifest data\eval_blind\manifest.json

python scripts\blind_eval.py freeze --cases data\eval_blind\cases.jsonl --labels data\eval_blind\labels.private.jsonl --manifest data\eval_blind\manifest.json

python scripts\blind_eval.py evaluate --cases data\eval_blind\cases.jsonl --labels data\eval_blind\labels.private.jsonl --manifest data\eval_blind\manifest.json --dense-retrieval on --dense-weight 0.30 --output reports\blind\blind_eval_results.json
```

正式评估默认关闭定向关键词规则。报告同时输出 Top3/Top5 微平均、按主模型宏平均、分场景结果、LLM trace 数量、稠密检索覆盖率以及与官方题库的近重复统计。

## 判定边界

- 少于 150 条会给出证据强度警告，但工具不会伪造补齐。
- 与官方问题完全重复、字符 n-gram 相似度达到阈值、泄露模型身份、作者与复核人相同、未通过人工复核或冻结后被修改时，工具拒绝生成正式评估报告。
- 自动生成、LLM 生成或开发者自己标注的数据不得填写人工独立声明。
- 即使所有软件检查通过，没有外部真人身份与评审记录证明时，也不能把报告改称正式独立盲测。
