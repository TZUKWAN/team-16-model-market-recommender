# 赛题需求对照表

## 总体定位

赛题要求是建设“大模型驱动的模型市场智能推荐助手”，核心不是单纯刷指标，而是让银行业务人员能够用自然语言找到合适模型、理解推荐依据、组合多个模型、落地调用和形成报告。

当前系统已经从原型推进为可运行 demo 系统：官方指标达标，官方 60 模型接入推荐体系，支持 LLM 安全配置路径、知识图谱证据、模型调用适配器、权限审计、合规边界、报告工作流、Docker 部署和端到端验收。

## 指标达标情况

最近命令：

```powershell
python scripts\run_official_eval.py --all
```

| 赛题指标 | 当前值 | 目标 | 状态 |
|---|---:|---:|---|
| 意图识别准确率 | 97.12% | >= 93% | 达标 |
| 标签转换准确率 | 99.04% | >= 90% | 达标 |
| Top3 命中率 | 93.53% | >= 85% | 达标 |
| Top5 命中率 | 97.12% | >= 92% | 达标 |
| 组合适配度 | 83.5 | >= 80 | 达标 |

主报告使用 `llm_mode=off`、`keyword_rules=false`、`hybrid_retrieval=true`，证明系统在无外部 API、无定向关键词刷分时仍可达标。修复融合量纲后，真实 Qwen 在测试拆分62条上完成62/62次重排，Top3/Top5为91.94%/96.77%，trace覆盖率100%，相对基线各净增3条且0退化。

## 赛题痛点到系统能力映射

| 赛题痛点/要求 | 系统实现 | 主要文件/证据 |
|---|---|---|
| 业务人员不会用模型语言检索 | 自然语言需求解析，输出领域、场景、标签、数据条件、期望输出和用户确认摘要 | `backend/app/services/demand_parser.py`，`POST /api/v1/parse-demand` |
| 需要大模型驱动 | Qwen3.5-122B-A10B 已完成测试拆分62/62真实受约束重排；Top3/Top5从无LLM基线87.10%/91.94%提升到91.94%/96.77%，各净增3条、0退化；无key时明确禁用 | `backend/app/services/llm_client.py`，`reports/official/eval_official_test_live_llm_results.json` |
| 模型资产难以统一管理 | 官方 60 模型、demo 105 模型统一纳管；默认单模型页面展示官方主榜和独立 Demo 参考区，官方指标/版本/组合保持隔离，支持 source 区分、校验和查询 | `backend/app/repositories/model_asset_repository.py`，`scripts/validate_model_assets.py` |
| 需要推荐 TopK 模型 | 最终冻结分拆合并报告全量 Top3/Top5 为93.53%/97.12%；BGE-M3 单独校准证据与最终融合报告分开记录 | `reports/official/eval_official_results.json`，`backend/app/services/hybrid_retriever.py`，`docs/eval/dense_retrieval_evidence.md` |
| 推荐必须可解释 | 推荐理由、证据卡片、评分拆解、图谱路径、适用边界、慎用场景 | `backend/app/services/explanation_generator.py`，前端推荐卡片 |
| 业务人员理解度需标准化问卷验证 | 已实现真人问卷活动、一次性邀请码、Q1-Q8 在线填写、去重、敏感信息拦截、完整受访者口径、分角色/分场景统计和匿名 CSV 导出；自动验收与真人证据强制隔离 | `backend/app/services/survey_service.py`，`backend/app/api/v1/surveys.py`，`frontend/src/components/SurveyPanel.tsx`，`docs/eval/standardized_questionnaire.md` |
| 多模型组合推荐 | 组合规划、节点流程、IO 兼容性、数据缺口、执行演示结果 | `backend/app/services/composition_planner.py`，`backend/app/services/composition_executor.py` |
| 结果要能落地 | demo model-market adapter 支持 invoke/task/result/schema，报告可包含模型结果样例 | `backend/app/integrations/demo_model_market_client.py`，`frontend/src/components/ModelResultTable.tsx` |
| 不能把 mock 冒充生产 | demo/real adapter 分离；real 未配置明确 503；报告和结果含脱敏/演示提示 | `backend/app/integrations/model_market_client.py`，`backend/app/services/compliance_service.py` |
| 银行场景需要权限审计 | 用户、角色、机构访问控制，审计事件记录与查询 | `backend/app/services/auth_service.py`，`backend/app/services/audit_service.py` |
| 合规和适用边界 | 推荐、调用结果和报告均输出合规提示、人工审核和使用边界 | `backend/app/services/compliance_service.py` |
| 数据不足需要提示 | 数据就绪度、缺失字段、替代建议和行动项 | `backend/app/services/data_readiness_service.py` |
| 系统必须可部署 | Docker Compose、前后端 Dockerfile、健康检查、HTTP smoke 验收 | `docker-compose.yml`，`reports/smoke_api_docker_results.json` |
| 需要演示验收 | 5 条业务路径 API smoke，前端构建通过 | `scripts/smoke_api.py`，`docs/demo/acceptance_scenarios.md` |

## 大模型边界

大模型负责：

- 复杂需求理解辅助。
- 多轮澄清辅助。
- 推荐解释润色与可读性增强。
- 合成数据表达增强。
- LLM-as-Judge 开发评估。

本地确定性系统负责：

- 官方数据加载。
- 模型 ID、模型名称、资产字段校验。
- 官方指标计算。
- 权限、审计、合规。
- 模型调用 adapter。
- 报告生成的结构化事实。

关键约束：

- 大模型不得创造不存在的模型 ID。
- 大模型输出不得覆盖官方 gold label。
- 推荐结果必须通过本地资产库校验。
- 无 LLM key 时不能生成伪 LLM 数据或伪 Judge 分数。

## 当前不足和后续优化

| 不足 | 影响 | 后续动作 |
|---|---|---|
| 未接真实银行模型市场 API | 不能证明生产模型调用闭环 | 等赛题方或银行提供 API 后，配置 real/http adapter 并做联调 |
| 独立盲测数据仍待真人采集 | 官方测试拆分已用于本轮受约束输出合同烟测，不能再视为完全未触碰的隐藏集 | 已实现 `scripts/blind_eval.py` 强制作者/复核人分离、私有答案、近重复和冻结哈希；下一步由独立成员真实出题复核 |
| 真人问卷尚无真实答卷 | 工程链路已完成，但当前不能把理解度指标声明为正式达标 | 组织不少于30人、正式建议50人的真实业务/风控/产品/运营/合规/科技人员，每人评价至少2个样例；附可核验人员或评审记录后出正式报告 |
| BGE-M3 已在 x86_64 CPU 竞赛容器验收，国产实机仍待外部复测 | 锁定 CPU 依赖、固定 revision、离线 SHA-256/1024维门禁；全量 417/417 稠密覆盖，Top3/Top5 为 93.53%/97.12% | 后续在指定国产算力环境复测安装、吞吐、延迟和并发；证据见 `reports/smoke/bge_m3_dense_runtime_acceptance_20260715.md` |
| 浏览器端到端验收已完成 | 五条路径逐项覆盖 Top5、详情、证据、缺口、组合、图谱、调用边界、对比、反馈、话术、报告和问卷入口；0 console error，桌面无横向溢出 | `reports/ui/five_path_browser_acceptance.md`；赛前仍应在比赛设备做一次环境回归 |
| 官方 60 模型覆盖有限 | 默认主榜仍只使用官方目录并披露低匹配，同时在独立、明确标注的 Demo 参考区展示补充候选；Demo 不进入官方结果、指标和组合 | 接入更多真实模型资产并扩展模型描述字段 |
| 知识图谱仍偏证据层 | 还不是唯一主排序引擎 | 增强图谱召回、路径权重和图谱可视化联动 |

## 证据清单

- 官方评估：`reports/official/eval_official_results.json`
- 无关键词混合检索消融：`reports/ablation/ablation_official_topk.json`
- 真实 Qwen 测试拆分重排：`reports/official/eval_official_test_live_llm_results.json`
- API 验收：`reports/smoke_api_results.json`
- Docker HTTP 验收：`reports/smoke_api_docker_results.json`
- 鲁棒性评估：`reports/robustness/robust_eval_results.json`
- LLM 合成 dry-run：`data/synthetic_llm/synthetic_llm_dry_run_template.manifest.json`
- LLM Judge skipped 报告：`reports/llm_judge/llm_judge_skipped.json`
- 真人问卷协议与系统入口：`docs/eval/standardized_questionnaire.md`、`POST /api/v1/surveys/campaigns`
- 问卷界面验收：`reports/ui/survey_desktop.png`、`reports/ui/survey_mobile_390x844.png`
- 状态记录：`.codex/CODEX_STATE.md`
