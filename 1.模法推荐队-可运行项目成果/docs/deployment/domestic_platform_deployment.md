# 国产化环境部署准备与外部验收手册

## 证据边界

当前仓库提供可移植部署包、Docker Compose、离线依赖准备、健康检查、性能脚本和回滚流程。尚未在真实鲲鹏、海光、飞腾、麒麟、统信或银行中间件环境完成部署，因此只能声明“具备国产环境部署准备”，不能声明“国产化适配验证通过”。

## 待外部验证矩阵

| 层级 | 候选环境 | 本仓库准备 | 外部必须记录 |
|---|---|---|---|
| CPU | 鲲鹏 ARM64、飞腾 ARM64、海光 x86_64 | Python/Node 多阶段容器，无本地二进制代码 | 型号、架构、核数、内存、镜像架构 |
| OS | 银河麒麟 V10、统信 UOS V20 | Linux 容器与 PowerShell 本机脚本分离 | OS 补丁、内核、容器运行时 |
| Python | 3.11 | 基础锁 `backend/requirements-lock.txt`；稠密锁 `backend/requirements-embeddings-lock.txt` | wheel 可用性、CPU 指令集、安装日志、pytest结果 |
| Node | 20 LTS | `npm ci` + Vite 静态产物 | npm离线安装和构建日志 |
| 数据库 | SQLite 本地正式默认；可后续适配达梦/人大金仓 | repository 边界、迁移/备份/恢复 | 并发、备份、恢复、文件系统语义 |
| LLM | OpenAI兼容网关 | 超时、熔断、缓存、fallback | 网络、TLS、模型名、成功率、延迟 |
| 模型市场 | HTTP合同适配器 | 8类合同沙箱通过 | 银行真实端点、任务ID、结果和银行确认 |

## 在线部署

```powershell
docker compose -f docker-compose.yml -f docker-compose.dense.yml --profile prepare run --rm dense-model-prepare
docker compose -f docker-compose.yml -f docker-compose.dense.yml build --pull
docker compose -f docker-compose.yml -f docker-compose.dense.yml up -d
python scripts/smoke_api.py --base-url http://127.0.0.1:8000 --output reports/smoke_api_docker_results.json
docker compose -f docker-compose.yml -f docker-compose.dense.yml down
```

竞赛交付使用 `competition_dense`；默认 `docker-compose.yml` 仅为轻量模式，不作为 BGE-M3 指标复现环境。

real 模式必须配置 JWT/OIDC 身份源；未配置时健康状态为 degraded，受保护操作拒绝服务。模型市场 URL+key 只表示 configured，首次合同合法响应前仍为 `real_connected=false`。

## 离线包准备

在与目标 CPU/OS/Python ABI 相同的联网机器执行：

```bash
python -m pip download -r backend/requirements-lock.txt -d offline/python-wheels/base
python -m pip download -r backend/requirements-embeddings-lock.txt -d offline/python-wheels/dense
npm ci --prefix frontend
npm cache add --cache offline/npm-cache --prefer-offline
docker save model-market-backend model-market-frontend -o offline/model-market-images.tar
```

离线环境先校验 Python wheel、镜像和 `data/models/bge-m3.manifest.json`，再使用 `pip install --no-index --find-links`、`npm ci --offline` 或 `docker load`。BGE-M3 权重不进入 Git，应随交付制品单独复制；运行时设置 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1`。下载成功不等于国产硬件推理通过。

## 健康与性能验收

1. `/api/v1/health` 必须为 healthy；竞赛模式下 `degraded` 属于验收失败。
2. `dense_runtime_ready=true`、`dense_available=true`、`dense_manifest_verified=true`、`dense_embedding_dimension=1024`。
3. 重启后 `dense_cache_hit=true`，417 条评估 `dense_available_case_count=417`。
4. `runtime_storage_ready=true`，认证模式与现场配置一致。
5. `python scripts/load_test_api.py --mode offline ...` 记录 p50/p95/p99、并发和错误率。
6. Qwen 只做受控小样本验收，记录真实成功率和延迟。
7. 保存 CPU、OS、容器、Python、Node、数据库和网络日志及截图。

## 回滚

1. 运行 `scripts/stop-project.ps1` 或 `docker compose down`。
2. 用 `scripts/migrate_runtime_storage.py restore --backup <file>` 恢复运行数据。
3. 用 `scripts/asset_catalog_versions.py rollback` 恢复资产 active 指针。
4. 重新加载上一镜像 tag，启动后执行 health、smoke 和关键五路径验收。
5. 回滚前后均保留哈希、时间、操作者、失败原因和验证结果。
