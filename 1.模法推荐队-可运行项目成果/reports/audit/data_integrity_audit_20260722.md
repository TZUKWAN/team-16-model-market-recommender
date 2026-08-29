# 官方数据划分、过拟合与来源完整性审计

生成时间：2026-07-22T15:32:53.970193+00:00
审计提交：cf8061e1563ad8d80f55dcfcc2cefa13bbfdf988
工作区是否含未提交修改：True（54 个状态项）

## 一、结论

在已检查的运行时代码和困难负例中，未发现把 test 样本直接用于训练；在已检查的项目代码中，也未发现 BGE-M3 微调入口。已知 train/val/test 的 Top-K 差距没有达到 10 个百分点的严重过拟合诊断阈值，但 test 结果在后续算法改动前已经可见，因此不是严格盲测。意图/标签弱标注同时依赖问句和答案模型名，困难负例元数据哈希又已失配，加上部分合成草稿字段参与结构化评分，整体存在中等偏高的证据偏差风险。

| 问题 | 结论 | 风险 |
|---|---|---|
| test 是否直接作为训练数据 | 未发现 | low |
| test 是否仍是独立盲测集 | 否 | medium |
| 已知划分是否出现大于 10 点的 train→holdout Top-K 落差 | 否 | medium |
| Intent/Tag 标签独立性 | 弱标注同时依赖问句和答案模型名 | high |
| 困难负例 metadata 哈希是否匹配 | 否 | medium |
| 非官方草稿字段是否影响排序 | 是 | medium |
| 综合风险 | 需要限定指标口径并补外部盲测 | medium_high |

## 二、数据划分完整性

- train / val / test：291 / 64 / 62。
- 跨 split ID 重复：0。
- 归一化文本完全重复：0。
- 词面近重复阈值：0.82；在该阈值下命中：0。
- 人工复核阈值：0.55；候选：3。
- 未执行语义向量级重复判定；词面阈值下为 0 不代表不存在语义改写。
- official 与 official_60 的 ID/归一化问句/gold ID 三元组一致：是。
- 划分类型：query-level split; not a model/entity holdout；三个 split 共同覆盖模型数：60。

最高跨 split 相似样本：

| 左侧 | 右侧 | 同标签 | 综合相似度 |
|---|---|---:|---:|
| train_0272 | val_0026 | 否 | 0.6132 |
| train_0199 | test_0031 | 是 | 0.5865 |
| train_0184 | val_0035 | 否 | 0.5615 |
| train_0265 | val_0050 | 否 | 0.5181 |
| train_0047 | val_0036 | 否 | 0.5018 |
| train_0204 | test_0047 | 否 | 0.4999 |
| train_0207 | test_0008 | 否 | 0.4992 |
| train_0130 | test_0018 | 否 | 0.4881 |
| train_0072 | val_0040 | 否 | 0.4809 |
| train_0248 | val_0031 | 否 | 0.4557 |

## 三、是否把 test 当成训练集

- 困难负例总数：795；来源 train case：280。
- 非 train ID：0；val/test ID 交集：0。
- 训练查询无法回溯到 train：0。
- 排序运行时代码直接读取 gold/test 文件：否。
- BGE-M3 常见微调入口命中：0（扫描 Python 文件 129 个）。
- 困难负例来源哈希匹配：False；输出哈希匹配：False。
- 困难负例复现状态：metadata_hashes_stale_current_pairs_need_regeneration_or_migration_record。
- 结论：在已检查的运行时代码、项目脚本和困难负例中，未发现 test 直接进入训练，也未发现 BGE-M3 微调入口。

注意：困难负例脚本的输入文件物理上包含 417 条全量记录，但脚本先筛选 train_，并在 mine() 内再次拒绝非 train ID。当前所有 pair 的 ID 与问句仍能回溯到 train，但 metadata 中的来源和输出 SHA-256 已与当前文件不符，所以不能宣称可按现有 metadata 逐字节复现。运行时代码检查只是对列出的路径做静态字符串扫描。

## 四、已知划分的泛化差距

评测来源：current_20260722。

| split | 样本量 | Top3 | Top5 | train-Top3 | train-Top5 |
|---|---:|---:|---:|---:|---:|
| train | 291 | 94.16% | 97.59% | 0 | 0 |
| val | 64 | 90.62% | 95.31% | 3.54 | 2.28 |
| test | 62 | 93.55% | 96.77% | 0.61 | 0.82 |

已知划分没有出现超过 10 个百分点的 train→holdout Top-K 落差，因此没有明显的严重经典过拟合迹象；但该阈值是诊断口径，且 test 已暴露，不能替代外部盲测。

## 五、test 是否仍然独立

- 首个已提交 test 结果：{"commit": "90dc33d5ca3de212290f4321d54de0bab87b5307", "date": "2026-06-30T19:22:49+08:00", "subject": "feat: evaluate official topk recommendations"}。
- 此后排序/解析/配置变更提交数：6。
- 当前状态：not_blind。
- dense 权重实验声明 selection 阶段读取 test 数：0；test 后再调参：False。

结论：dense 权重 0.5 的局部实验有 val-only 选择证据；但全项目历史中 test 结果先于后续算法改动公开，所以不能把当前 test 描述为从未查看的一次性盲测。时间顺序只能证明暴露，不能证明开发者有意按 test 调参。

## 六、标签独立性与答案依赖

- 417 条官方问题中 needs_review=true：417。
- expected_tags 由 query + gold_model_name 推导：True。
- intent_task 由 query + gold_model_name 推导：True。
- test 中保守模型名/核心名直现率：3.23%。

TopK gold model names come from the official Excel answer column. Intent/task/tag labels are local weak annotations derived from both the query and the gold answer model name, and remain marked needs_review. Intent/tag accuracy therefore has direct label-dependency risk and is not independent human-labelled generalization evidence.

## 七、合成数据与非官方字段

- 规则合成数据生成器读取 questions_all：True。
- 当前运行时排序直接引用合成问题集：False。
- synthetic_draft 字段：historical_cases、performance_metrics。
- 结构化排序读取 performance_metrics：True；读取 historical_cases：True。

现有规则合成语料由 questions_all（含 train/val/test）派生；当前运行时排序没有读取它。如果未来用于训练或调参，必须从 train-only 重新生成。

performance_metrics 与 historical_cases 是未核验的 synthetic_draft。当前结构化排序会读取它们，因此它们可以影响排序，但不得被当作银行生产证据。

## 八、外部盲测

- 已有盲测协议脚本：True。
- 仓库内实际盲测 cases/labels 文件数：0。
- 当前存在独立盲测证据：False。

## 九、允许与不允许的结论口径

- TopK 仅表示对已知官方 60 模型目录和已公开 417 问题分布的检索命中率。
- Intent/Tag 指标不得描述为独立人工标注集上的泛化准确率。
- 当前 test 不得描述为从未查看的最终盲测集。
- 困难负例元数据哈希失配前，不得宣称该制品可按现有 metadata 逐字节复现。
- performance_metrics 与 historical_cases 为 synthetic_draft，不是银行生产验收证据。
- 规则/LLM 合成数据不得与官方样本或真实银行生产数据混称。

## 十、建议控制措施

1. 建立全新外部盲测集：由未参与开发人员保管标签，冻结代码后一次性评测。
2. 重新从 train-only 官方问题生成任何用于训练/调参的合成语料；禁止 questions_all 进入训练生成链。
3. 对 intent/tag 建立人工复核标签集，并与当前弱标注指标分开展示。
4. 重新生成困难负例或补充可审计的 ID 迁移记录，并更新来源/输出 SHA-256。
5. 官方排序默认禁用或显式降权 synthetic_draft 性能指标与案例，除非完成来源核验。
6. 同时报告模型名遮蔽、跨表达和跨机构场景结果，避免只报原始 Top3/Top5。
