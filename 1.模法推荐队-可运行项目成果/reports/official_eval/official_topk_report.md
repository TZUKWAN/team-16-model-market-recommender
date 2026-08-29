# 官方 TopK 评测报告（当前 competition_dense 口径）

生成时间：2026-07-24T12:20:09.306343+00:00

数据源：scripts/run_official_eval.py 在 competition_dense（BGE-M3，1024 维，清单已校验）下的 val/test 实跑结果，由 scripts/refresh_official_eval_reports.py 转换为页面读取格式。与 reports/official、reports/audit 的口径一致；2026-06-30 的稀疏口径旧文件已被本报告取代。

| 划分 | 样本数 | Top1 | Top3 | Top5 |
|---|---:|---:|---:|---:|
| val | 64 | 81.2% | 90.6% | 95.3% |
| test | 62 | 79.0% | 93.5% | 96.8% |

说明：TopK 为对已知官方 60 模型目录和已公开 417 问题分布的检索命中率；test 已历史暴露，不是严格盲测集。
