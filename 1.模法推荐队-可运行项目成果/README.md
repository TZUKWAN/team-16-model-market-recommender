# 银行模型市场智能推荐助手

面向银行模型市场的智能推荐系统。系统把业务人员的自然语言需求解析为模型语言，基于官方模型资产库、标签体系、知识图谱证据、数据缺口诊断、合规边界和审计记录，输出单模型 TopK 推荐、多模型组合方案、脱敏模型调用结果和推荐报告。

本仓库不包含真实客户数据、手机号、身份证号、银行卡号或生产银行接口密钥。所有密钥必须通过本机环境变量或部署平台密钥管理注入，不能写入代码、文档、日志或提交记录。

## 当前状态

最近验证日期：2026-07-15。

| 项目 | 结果 | 证据 |
|---|---:|---|
| 后端测试 | 379 passed，1 warning | `pytest backend\tests -q` |
| 前端构建 | 通过，2642 modules | `npm run build` |
| 官方指标 | 全达标 | `python scripts\run_official_eval.py --all` |
| 无关键词混合检索消融 | 全量 Top3/Top5 达标 | `reports/ablation/ablation_official_topk.json` |
| 真实 Qwen 测试集重排 | Top3 91.94%、Top5 96.77%，trace 62/62 | `reports/official/eval_official_test_live_llm_results.json` |
| 真人问卷界面验收 | 桌面端和 390x844 移动端无横向溢出 | `reports/ui/survey_desktop.png`、`reports/ui/survey_mobile_390x844.png` |
| 整合版前端交互验收 | 桌面/390x844 主链路、故障重试、三格式报告通过 | `reports/ui/integrated_frontend_acceptance_20260715.md` |
| API 端到端验收 | 5/5 通过 | `reports/smoke_api_results.json` |
| Windows/Docker 运行验收 | start/status/stop 通过，2/2 容器 healthy | `reports/smoke/integrated_runtime_validation_20260715.md` |
| 鲁棒扰动集 | 通过阈值 | `reports/robustness/robust_eval_results.json` |
| 密钥扫描 | 未发现疑似泄漏 | `python scripts\check_no_secret_leak.py` |

官方评估指标：

| 指标 | 当前值 | 目标 |
|---|---:|---:|
| 意图识别准确率 | 97.12% | >= 93% |
| 标签转换准确率 | 99.04% | >= 90% |
| Top3 命中率 | 93.53% | >= 85% |
| Top5 命中率 | 97.12% | >= 92% |
| 组合适配度 | 83.5 | >= 80 |

上述主指标默认关闭 LLM 和针对模型名称的定向关键词规则，开启事实模型知识卡混合检索，可离线复现。修复本地分与LLM位置分量纲后，真实 Qwen 受约束重排在官方测试拆分62条上达到 Top3 `91.94%`、Top5 `96.77%`，相对基线分别提升 `4.84/4.83` 个百分点，62/62条含真实 trace且0条退化；该报告用于证明大模型增益，不替代离线主指标。

## 核心能力

- 需求解析：规则 + 可选 LLM 的混合解析，支持领域、业务阶段、客群、产品、风险、输出、数据条件、约束和澄清问题。
- 模型推荐：统一资产库包含官方 60 模型、demo 105 模型和扩展模型；默认单模型推荐返回官方 Top5 主榜，并在独立区域附带 Demo Top3 参考候选。两类结果分别排序、明确标注，Demo 不计入官方评估、版本榜单或组合推荐；组合方案仍只使用官方模型。推荐使用事实知识卡字符 n-gram 检索、结构化评分、图谱证据和可选 BGE-M3 稠密检索。
- 稠密检索验收：真实 BGE-M3 在验证集将 Top3/Top5 提升至 `89.06%/95.31%`，测试集提升至 `90.32%/95.16%`；417条稠密覆盖 `417/417`，并提供知识卡向量缓存。
- 大模型重排：Qwen 只对本地候选 ID 做 Top10 受约束重排；本地候选分先进行候选池 Min-Max 归一化，再按本地65% + LLM排序35%融合，避免不同量纲让LLM越权；非法 ID、缺失 ID、修复、缓存和 trace 均有审计记录。
- 知识图谱：提供模型、标签、字段、场景、组合关系的查询和路径证据。
- 组合方案：输出多模型流程、节点、输入输出兼容性、数据缺口和脱敏执行结果。
- 模型调用：本地 demo adapter 支持任务提交、状态查询、结果查询和结果 schema；real/http adapter 未配置时明确返回 503，不静默 fallback。
- 权限审计：支持本地角色/机构访问控制、模型访问校验、任务访问校验和审计日志。
- 合规边界：推荐、调用结果和报告中展示脱敏、适用边界、人工审核和合规提示。
- 真人问卷：推荐结果页可发起标准化 Q1-Q8 理解度评价；后端提供一次性邀请码、重复提交拦截、敏感信息拦截、完整受访者统计、匿名 CSV 导出和审计。自动验收活动与真人证据强制隔离。
- 报告工作流：后端生成推荐报告，前端支持查看、复制、打印以及 Markdown、DOCX、PDF 下载。
- LLM 能力：已支持 BigModel/OpenAI-compatible Chat Completions 的安全配置路径；无 key 时明确禁用，不伪造调用结果。

## 项目结构

```text
team-16-main/
├── backend/                 # FastAPI 后端
├── frontend/                # React + TypeScript 前端
├── data/
│   ├── official/            # 官方 417 问题 + 60 模型
│   ├── knowledge/           # 标签、字段、组合模板、图谱数据
│   ├── synthetic/           # 规则合成开发数据
│   ├── synthetic_llm/       # LLM 合成脚本 dry-run / live 输出目录
│   └── eval_official/       # 官方评估集
├── docs/                    # 数据、评估、演示、赛题对照文档
├── reports/                 # 评估、验收、鲁棒性报告
├── scripts/                 # 校验、评估、smoke、合成数据脚本
├── docker-compose.yml
└── .env.example
```

## 快速启动

### 竞赛压缩包一键运行

正式交付包携带固定 revision 和 SHA-256 清单校验的 BGE-M3 模型制品。Windows
评审设备在启动 Docker Desktop 后，可直接双击仓库根目录的
`start-competition.bat`。脚本会校验模型、构建稠密运行时、等待严格健康门禁并打开
前端；停止时双击 `stop-competition.bat`。

源码仓库仍不提交约 2.30 GB 的 `data/models/`。维护者使用
`scripts/package-competition.ps1` 从当前可审计工作树显式加入模型并生成 Zip64
交付包。打包使用 Python 标准库生成 Unicode 安全的 Zip64，并在重新解压后逐一
比对全部 Git 跟踪文件的路径和 SHA-256；详细操作见 `RUN_INSTRUCTIONS_ZH.txt`。

### 本地后端

推荐使用项目管理脚本（后端 8010、前端 5173，带依赖/端口/健康检查和安全 PID 管理）：

```powershell
.\scripts\start-project.ps1 -Offline
.\scripts\status-project.ps1
.\scripts\stop-project.ps1
```

手工启动仅用于开发调试：

```powershell
pip install -r backend\requirements.txt
$env:PYTHONPATH='backend'
python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

后端地址：`http://localhost:8000`
OpenAPI：`http://localhost:8000/docs`

### 本地前端

```powershell
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:5173`

### Docker Compose

默认轻量/demo 模式不需要 `.env` 文件；该模式只使用稀疏检索，不会隐式下载 BGE-M3：

```powershell
docker compose up --build
```

竞赛稠密模式先准备一次固定 revision + SHA-256 清单的本地模型制品，再使用叠加配置启动：

```powershell
docker compose -f docker-compose.yml -f docker-compose.dense.yml --profile prepare run --rm dense-model-prepare
docker compose -f docker-compose.yml -f docker-compose.dense.yml up --build -d
```

模型制品写入 Git 忽略的 `data/models/`。竞赛模式强制离线加载、1024 维和清单校验；任一条件失败时 `/api/v1/health` 为 `degraded`，推荐接口返回 503，不会静默回退稀疏排序。

默认地址：

- 后端：`http://localhost:8000`
- 前端：`http://localhost:3000`

如果 3000 被占用：

```powershell
$env:FRONTEND_PORT='3001'
docker compose up --build
```

最近已验证：

- `docker compose config --quiet` 通过。
- `docker compose build` 通过。
- `FRONTEND_PORT=3001 docker compose up -d` 后，backend/frontend 均 healthy。
- `python scripts\smoke_api.py --base-url http://localhost:8000 --output reports\smoke_api_docker_results.json` 通过 5/5。

## 环境变量

复制 `.env.example` 为 `.env` 仅用于本地，不要提交 `.env`。

| 变量 | 说明 | 默认 |
|---|---|---|
| `ENABLE_MOCK` | 是否启用演示/本地默认能力 | `true` |
| `MODEL_MARKET_ADAPTER` | `demo` 或 `real`/`http` | `demo` |
| `MODEL_MARKET_BASE_URL` | 真实模型市场地址 | 空 |
| `MODEL_MARKET_API_KEY` | 真实模型市场密钥 | 空 |
| `LLM_PROVIDER` | `mock`、`bigmodel`、`openai`、`deepseek` | `mock` |
| `LLM_BASE_URL` | LLM Chat Completions 地址 | 空 |
| `LLM_MODEL` | LLM 模型名 | 空 |
| `LLM_API_KEY` | LLM 密钥 | 空 |
| `RETRIEVAL_RUNTIME_MODE` | `light` 或强制稠密的 `competition_dense` | `light` |
| `HYBRID_DENSE_ENABLED` | 是否启用本地稠密检索 | `false` |
| `HYBRID_DENSE_WEIGHT` | 稠密分在检索融合中的占比 | `0.50` |
| `HYBRID_DENSE_MODEL` | SentenceTransformer 模型 | `BAAI/bge-m3` |
| `HYBRID_DENSE_REQUIRED` | 稠密不可用时是否拒绝推荐 | `false` |
| `HYBRID_DENSE_OFFLINE` | 是否禁止运行时联网取权重 | `false` |
| `HYBRID_DENSE_EXPECTED_DIMENSION` | 期望向量维度 | `1024` |
| `HYBRID_DENSE_EXPECTED_REVISION` | 清单必须匹配的模型 commit | 空（竞赛 Compose 固定为已验收 commit） |
| `HYBRID_DENSE_MANIFEST` | 本地模型 SHA-256 清单 | 空 |
| `HYBRID_DENSE_VERIFY_MANIFEST` | 加载前是否校验全部权重文件 | `false` |
| `HYBRID_DENSE_CACHE_ENABLED` | 缓存模型知识卡向量 | `true` |
| `HYBRID_DENSE_CACHE_DIR` | 模型知识卡向量缓存目录 | `data/cache/embeddings` |
| `VITE_API_BASE_URL` | 前端调用后端地址 | `http://localhost:8000` |
| `BACKEND_PORT` | Docker 后端宿主端口 | `8000` |
| `FRONTEND_PORT` | Docker 前端宿主端口 | `3000` |

OpenAI-compatible Qwen 网关配置示例，只能放入本地环境变量或本地 `.env`：

```env
LLM_PROVIDER=openai
LLM_BASE_URL=http://218.197.140.7:3001/v1/
LLM_MODEL=Qwen3.5-122B-A10B
LLM_API_KEY=<set-in-local-env-only>
```

BigModel / GLM 也可用同一客户端配置：

```env
LLM_PROVIDER=bigmodel
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/chat/completions
LLM_MODEL=glm-4.7-flash
LLM_API_KEY=<set-in-local-env-only>
```

BGE-M3 运行时由 `backend/requirements-embeddings-lock.txt` 锁定 CPU PyTorch 与 Sentence Transformers。轻量模式允许明确使用稀疏检索；`competition_dense` 模式不允许回退，并要求本地权重、固定 revision、逐文件 SHA-256、1024 维和向量缓存全部就绪。只有健康接口 `dense_available=true` 且评估报告 `dense_available_case_count` 等于样本数时，才能说明稠密检索真实参与；校准边界见 [BGE-M3 稠密检索校准记录](docs/eval/dense_retrieval_evidence.md)，容器交付验收见 `reports/smoke/bge_m3_dense_runtime_acceptance_20260715.md`。

## 验证命令

```powershell
pytest backend\tests -q
npm run build
python scripts\validate_data.py
python scripts\validate_model_assets.py
python scripts\check_no_secret_leak.py
python scripts\run_official_eval.py --all
python scripts\smoke_api.py
python scripts\run_robust_eval.py
```

Docker HTTP 验收：

```powershell
docker compose up -d
python scripts\smoke_api.py --base-url http://localhost:8000 --output reports\smoke_api_docker_results.json
docker compose down
```

竞赛稠密验收必须使用 `docker-compose.dense.yml`，并检查健康响应中的 `dense_runtime_ready`、`dense_manifest_verified`、`dense_embedding_dimension` 和 `dense_cache_hit`。

## 关键脚本

| 脚本 | 用途 |
|---|---|
| `scripts/run_official_eval.py --all` | 官方指标评估 |
| `backend/scripts/prepare_dense_model.py` | 下载固定 BGE-M3 revision、离线探针并生成 SHA-256 清单 |
| `scripts/run_robust_eval.py` | 2,085 条扰动集鲁棒性评估 |
| `scripts/blind_eval.py` | 独立盲测校验、冻结和私有答案评估 |
| `scripts/mine_hard_negatives.py` | 仅从训练拆分挖同领域困难负样本 |
| `scripts/create_survey_campaign.py` | 创建真人解释问卷活动和一次性私有邀请码 |
| `scripts/smoke_api.py` | 5 条业务路径 API 端到端验收 |
| `scripts/generate_synthetic_official_data.py` | 规则模板合成开发数据 |
| `scripts/generate_synthetic_with_llm.py` | LLM 增强合成数据生成器；无 key 时 SKIP |
| `scripts/run_explanation_judge_with_llm.py` | LLM-as-Judge 开发评估；无 key 时 SKIP |
| `scripts/check_no_secret_leak.py` | 密钥泄漏扫描 |

### Runtime storage operations

Mutable sessions, audit events, feedback, surveys and recommendation versions use
SQLite by default at `data/runtime/runtime.db`. Legacy JSON/JSONL remains supported
for migration and isolated demo/test instances. Back up before importing old data:

```powershell
python scripts/migrate_runtime_storage.py migrate --backup data/runtime/pre_migration.db --report reports/runtime/migration.json
python scripts/migrate_runtime_storage.py check
python scripts/migrate_runtime_storage.py export --output-dir data/runtime_export
python scripts/migrate_runtime_storage.py restore --backup data/runtime/pre_migration.db
```

`restore` is explicit and validates the backup before replacing the active database.
The health endpoint reports `runtime_storage_ready` and the SQLite integrity result.

## 数据说明

| 数据 | 规模 | 说明 |
|---|---:|---|
| official | 417 问题，60 模型 | 竞赛官方数据，使用 `OFFICIAL_001` 到 `OFFICIAL_060` |
| demo | 105 模型 | 本地脱敏演示模型，使用 `RISK_`、`MKT_`、`OPS_` |
| synthetic | 3,000 条 | 规则模板合成开发数据 |
| robustness | 2,085 条 | 官方问题的同义、口语、噪声、长上下文、混合上下文扰动 |
| synthetic_llm dry-run | 4 条样例 | 仅验证字段和链路，不能称为 LLM 生成数据 |

默认单模型策略为 `official_then_demo`：请求不传 `model_source` 时，`recommendations` 返回 `official-v1` 的官方 Top5 主榜，`demo_references` 独立返回 `demo-v1` 的 Demo Top3 参考候选。Demo 参考不参与官方指标、推荐版本记录或组合推荐，也不会替换官方结果；官方目录缺失时仍返回结构化错误。传 `official` 或 `demo` 可显式请求单一目录，`demo_top_k=0` 可关闭默认 Demo 参考。

### 官方模型 ID 统一

`data/official_60/models.jsonl` 的 60 行顺序是 `official-v1` 的权威 ID 顺序。整合时已把 `feature-v1` 映射到该顺序：60 个映射中 57 个 ID 发生变化，共迁移 21,924 处引用并扫描 23,091 处官方 ID。417 条官方问题、30 个组合案例和 95 对组合 gold 均已校验；外部消费者如保存过旧 `feature-v1` ID，应使用 `data/official_60/official_id_mapping.json` 迁移。完整证据见 `reports/data_governance/official_id_migration_report.json`。

LLM live 合成数据尚未生成。当前本机密钥已经安全注入并用于真实 Qwen 需求解析和受约束重排，但没有执行 live 合成数据脚本，因此不能把 dry-run 样例称为大模型生成数据。

## API 清单

所有 API 统一前缀 `/api/v1`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查、运行模式、LLM/模型市场状态 |
| POST | `/parse-demand` | 自然语言需求解析 |
| POST | `/recommend-models` | 单模型 TopK 推荐 |
| POST | `/recommend-composition` | 多模型组合推荐和执行演示 |
| GET | `/models/{model_id}` | 模型详情 |
| POST | `/models/{model_id}/invoke` | 模型调用 |
| GET | `/tasks/{task_id}` | 任务状态 |
| GET | `/tasks/{task_id}/result` | 模型结果 |
| POST | `/reports/recommendation` | 推荐报告 |
| GET | `/evaluation/metrics` | 官方评估指标 |
| POST | `/surveys/campaigns` | 创建问卷活动和一次性邀请码（管理员） |
| GET | `/surveys/campaigns/{campaign_id}` | 获取问卷定义 |
| POST | `/surveys/responses` | 提交匿名问卷答卷 |
| GET | `/surveys/campaigns/{campaign_id}/summary` | 获取理解度统计（管理员） |
| GET | `/surveys/campaigns/{campaign_id}/export.csv` | 导出匿名答卷（管理员） |
| GET | `/audit/events` | 审计事件查询 |

## 五条演示路径

详见 [验收场景](./docs/demo/acceptance_scenarios.md)。

- 县域新客首贷营销。
- 农户小额贷款贷前风控。
- 对公贷款贷后预警。
- 网点客流与排班运营。
- 高价值客户流失挽留。

## 真实边界

- 真实银行模型市场 API 尚未由赛题方或用户提供；当前 real/http adapter 已有接口形态，未配置时返回明确错误。
- 独立人工盲测尚未采集；已提供作者/复核人分离、私有答案、SHA-256 冻结、模型身份泄漏检查和官方题库近重复检查工具，不能把开发者自测冒充正式盲测。
- 真人标准化问卷的在线采集、统计和导出链路已经实现，但当前尚无可核验的真实受访者答卷，因此不能声明“业务人员理解度 >= 90%”正式达标；自动验收答卷永远不计入真人指标。
- demo adapter 返回的是脱敏演示结果，不是生产模型调用结果。
- 默认单模型页面以官方 60 模型为主榜，并在独立区域显示 demo 参考候选；组合目录仍只用官方模型。Demo 不能冒充官方结果，也不能作为官方目录缺失时的隐式兜底。
- LLM 解析、解释、合成数据、Judge 均需要本地安全注入密钥；无 key 时系统不伪造调用。
- 官方指标是基于官方 417 问题和 60 模型计算，不代表隐藏集或生产场景必然同等表现。
- 合成数据只用于开发、测试、鲁棒性和演示，不可冒充官方数据或真实银行数据。

## 文档入口

- [赛题需求对照表](./docs/COMPETITION_REQUIREMENT_MAPPING.md)
- [官方主榜 + Demo 参考区验收记录](./reports/ui/demo_reference_policy_acceptance_20260715.md)
- [统一证据索引](./docs/EVIDENCE_INDEX.md)
- [现场演示与故障切换](./docs/demo/onsite_runbook.md)
- [真系统任务清单](./docs/TRUE_SYSTEM_TASK_LIST.md)
- [验收场景](./docs/demo/acceptance_scenarios.md)
- [整合版前端验收](./reports/ui/integrated_frontend_acceptance_20260715.md)
- [整合版运行与容器验收](./reports/smoke/integrated_runtime_validation_20260715.md)
- [BGE-M3 竞赛运行时验收](./reports/smoke/bge_m3_dense_runtime_acceptance_20260715.md)
- [四分支整合记录与 PR 审查指南](./docs/INTEGRATION_RECORD_20260715.md)
- [演示脚本](./docs/demo/demo_script.md)
- [数据集说明](./docs/data/dataset_card.md)
- [合成数据说明](./docs/data/synthetic_dataset_card.md)
- [标签体系](./docs/data/tag_taxonomy.md)
- [评估方法](./docs/eval/evaluation_method.md)
- [标准化理解度问卷](./docs/eval/standardized_questionnaire.md)
- [算法说明](./docs/eval/algorithm_method.md)
