# 消融实验报告：去定向关键词后的混合检索与真实 Qwen 增益

> 最近验证：2026-07-10
> 官方 TopK 数据：417 条（train=291、val=64、test=62）
> 主脚本：`scripts/run_official_eval.py`

## 1. 评估原则

主指标必须可离线复现，因此默认关闭 LLM 和定向关键词规则，只启用事实模型知识卡混合检索。真实 Qwen 重排单独生成报告，并且只有记录真实 trace 才算 LLM 执行；“请求开启但未配置”不会记为 LLM 模式。

模型知识卡只使用模型名称、官方描述、业务场景、客群、能力、输入输出和边界等事实字段，不把规则补全的性能数字或历史案例用于检索文本。

## 2. 全量 417 条离线消融

| 模式 | 定向关键词 | 混合检索 | LLM | Top3 | Top5 |
|---|---:|---:|---:|---:|---:|
| `legacy_keyword_rule` | 开 | 关 | 关 | 97.12% | 100.00% |
| `no_keyword_no_hybrid` | 关 | 关 | 关 | 78.66% | 86.33% |
| `hybrid_no_keyword` | 关 | 开 | 关 | **85.61%** | **92.33%** |

混合检索相对无关键词旧底座提升 Top3 `6.95` 个百分点、Top5 `6.00` 个百分点，在不依赖定向关键词的情况下重新跨过赛题阈值。

## 3. 真实 Qwen 测试拆分结果

固定测试拆分 62 条，规则解析保持关闭 LLM，仅让 Qwen 对本地 Top30 候选返回 Top10 ID；最终排序融合本地证据分 65% 与 LLM 排序分 35%。

| 模式 | Top3 | Top5 | 命中数 |
|---|---:|---:|---:|
| 混合检索，无 LLM | 87.10% | 91.94% | 54/62、57/62 |
| 混合检索 + 真实 Qwen | **91.94%** | **96.77%** | 57/62、60/62 |

真实调用审计：

- 重排尝试：62/62。
- 重排成功：62/62。
- 含 trace 的样本：62/62，覆盖率 100%。
- 唯一 trace：62 个。
- JSON 修复：0 次。
- 非法候选 ID：0 个。
- 缺失 ID：0 个。
- Top3 净改善：3 条，退化 0 条。
- Top5 净改善：3 条，退化 0 条。

这证明大模型不是仅用于解释文本，而是对推荐排序产生了可测量、可追溯的正向增益。

## 4. 约束与降级

- LLM 只能返回显式允许列表中的 10 个候选 ID。
- 非法 ID 被本地资产库拒绝并写入审计。
- 输出不足 10 个时最多修复一次；仍失败则回退本地混合检索。
- 相同需求和候选集合使用进程内缓存，避免重复调用。
- 本地候选分先在候选池内归一到0-100，再与LLM位置分按65%/35%融合；避免本地原始分值范围较低时，35%的LLM权重实际越权覆盖强本地证据。

## 5. 可复现命令

```powershell
# 离线主指标：无 LLM、无定向关键词、混合检索开启
python scripts\run_official_eval.py --all

# 三路离线消融
python scripts\run_official_eval.py --ablation --split all

# 真实 Qwen 测试拆分重排，必须有真实 key，否则失败
python scripts\run_official_eval.py --topk --split test --llm-mode on --llm-scope rerank --keyword-rules off --hybrid-retrieval on --require-live-llm --output reports\official\eval_official_test_live_llm_results.json
```

证据文件：

- `reports/official/eval_official_results.json`
- `reports/ablation/ablation_official_topk.json`
- `reports/official/eval_official_test_live_llm_results.json`

## 6. 局限

- 本轮先用 5 个测试失败样本验证并简化了 Qwen 输出合同，再跑完整 62 条。因此该测试拆分不再是完全未触碰的独立盲测，不能替代赛事隐藏集。
- 官方标注包含 `annotation_version=1.0_weak` 和 `needs_review=true`，仍需人工复核歧义需求和等效模型。
- BGE-M3 已单独完成真实 CPU 验收：417/417 条有稠密分，全量 Top3/Top5 为 `90.65%/95.20%`；该结果与 Qwen 报告分开，不把两条链路重复包装成组合增益。
- 独立盲测采集尚未完成；现已提供作者/复核人分离、私有答案、模型身份泄漏检查、官方题库近重复检查和 SHA-256 冻结工具，但仍必须由真实独立成员出题和复核。
