# 现场演示与故障切换手册

目标时长：5–8 分钟。正式竞赛演示优先使用 `docker-compose.dense.yml`（默认后端 8000、前端 3000，可用环境变量改端口）；Windows 8010/5173 轻量启动只作为无法运行稠密容器时的明确降级预案。

## 演示前检查

```powershell
docker compose -f docker-compose.yml -f docker-compose.dense.yml up -d
docker compose -f docker-compose.yml -f docker-compose.dense.yml ps
```

确认：

1. 后端和前端状态均为 managed/healthy。
2. 系统状态显示官方数据已加载、165 个模型、资产问题为 0。
3. `认证模式=Demo Header（非生产认证）`、`模型市场=demo/未连接`。
4. 系统状态显示 `BGE-M3 / 1024维 / 清单已校验`；健康接口为 `competition_dense`、`dense_available=true`、`dense_cache_hit=true`。
5. Offline 演示时 LLM 显示未启用，话术明确标记典型模板；需要展示真实 LLM 时只展示已冻结证据，不现场无限调用。

## 5–8 分钟主线

### 0:00–0:45 定位与边界

打开 `http://127.0.0.1:5173/`。

话术：系统把自然语言需求转成结构化模型检索和可落地方案。当前连接本地脱敏模型市场适配器；真实银行接口因未提供而未联调，但合同、权限、审计和错误边界已准备完毕。

### 0:45–2:30 推荐主线

选择“路径1：客户营销”，点击“解析需求”和“生成模型推荐”。依次展示：

- 意图、场景、客群、产品、输出、数据条件和标签置信度。
- Top5、评分拆解、模型详情、证据来源、适用/慎用/合规边界。
- 数据缺口、补齐动作和替代模型。

### 2:30–4:30 F1-F5 创新点

1. F1：选择两个模型“加入对比”，解释效果预估的来源等级与“非生产决策”边界。
2. F2：点击采纳/不采纳/收藏，说明只有达到门槛的 human 反馈才会小幅影响排序。
3. F3：点击“生成话术”；Offline 是明确模板。真实 Qwen 9/9 证据见 `reports/scenario_scripts/qwen_live_acceptance.json`。
4. F4：点击“查看图谱”，展示需求路径高亮、节点聚焦、邻居下钻和返回。
5. F5：点击“生成一页纸报告”，展示 Markdown/DOCX/PDF 与持久化推荐版本。

### 4:30–5:30 组合与调用边界

点击“生成组合方案”和“调用模型”。强调：

- 组合会给出节点、IO 兼容、缺失字段、降级/阻断原因。
- 调用结果来自 demo 脱敏 adapter，不是生产模型效果。
- real/http 未配置时返回明确错误，不会静默伪造成功。

### 5:30–6:30 指标与证据

加载评估指标：97.12%、99.04%、93.53%、97.12%、83.5。说明指标来自官方 417 题/60 模型与 30 条组合样本；不等同于独立盲测或生产效果。

### 6:30–7:30 问卷与外部待办

打开“评价推荐解释”，展示标准化 Q1-Q8、邀请码和匿名提交。说明工程链路完成，但没有可核验真人答卷前不声明理解度正式达标。

## 故障切换

### LLM 超时或无 Key

- 页面应显示 `LLM：未启用` 或明确 fallback 原因。
- 继续使用规则解析、本地检索和典型话术模板。
- 展示冻结真实调用证据，不在现场反复重试或暴露 Key。

### BGE-M3 未就绪

- `competition_dense` 下健康状态应为 degraded，推荐接口应返回 503，禁止把稀疏回退称为正式稠密结果。
- 检查 `data/models/bge-m3.manifest.json`、`dense_error_code`、容器日志和本地模型目录。
- 若只能切换轻量模式，必须明确说明本次现场仅验证交互链路，并展示冻结的 417/417 稠密证据。

### 后端不可用

```powershell
.\scripts\status-project.ps1
.\scripts\stop-project.ps1
.\scripts\start-project.ps1 -Offline
```

不要手工批量杀进程。脚本只管理记录的 PID、启动时间、命令和端口。

### 端口冲突

启动脚本会拒绝占用未知进程的端口。不要停止 8000/8001 的其他项目；先确认 8010/5173 占用者，再使用另一个显式端口启动本项目。

### 模型市场不可用

- 保持 `MODEL_MARKET_ADAPTER=demo` 展示脱敏调用。
- 展示合同沙箱 8/8 和 `real_connected=false`。
- 禁止说“真实银行 API 已接入”。

### 页面或网络异常

- 使用 `reports/ui/five_path_desktop_final.png`、`reports/ui/f4_graph_desktop_path_highlight.png` 作为截图备份。
- 使用 `reports/export_acceptance/` 中已渲染报告作为文件备份。
- 使用 `docs/EVIDENCE_INDEX.md` 快速定位原始 JSON 和复现命令。

## 禁止表述

- “已连接真实银行模型市场/生产模型”。
- “自动问卷证明真人理解度达标”。
- “合成数据或 LLM Judge 是真实业务效果”。
- “推断或合成的模型指标已经银行验证”。
- “合同沙箱通过等于银行联调完成”。

## 演示后关闭

```powershell
docker compose -f docker-compose.yml -f docker-compose.dense.yml down
```

确认 8010 和 5173 已释放，且未影响其他项目。
