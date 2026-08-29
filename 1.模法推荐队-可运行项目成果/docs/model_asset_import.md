# 模型资产批量导入说明

本文档对应 `docs/TRUE_SYSTEM_TASK_LIST.md` 的 `2.2 268 模型导入机制`。

## 支持格式

`scripts/import_model_assets.py` 支持：

- `.jsonl`：每行一个模型对象。
- `.json`：单个对象或对象数组。
- `.csv`：首行为字段名。
- `.xlsx/.xlsm`：首个工作表，第一行为字段名。
- 目录：读取目录下的单模型 `.json` 文件，主要用于现有 `data/knowledge` demo 模型复验。

CSV/XLSX 表头应使用 [model_catalog_import_template.json](../data/templates/model_catalog_import_template.json) 中的 `fields[].key`。

## 常用命令

官方 60 模型 dry-run：

```powershell
python scripts\import_model_assets.py --input data\official\model_catalog_structured.jsonl --output reports\imports\official_models_imported.jsonl --source official --dry-run
```

现有 105 个 demo 模型 dry-run：

```powershell
python scripts\import_model_assets.py --input data\knowledge --output reports\imports\demo_models_imported.jsonl --source demo --dry-run
```

真实导入到标准 JSONL：

```powershell
python scripts\import_model_assets.py --input data\raw\model_catalog_268.xlsx --output data\imports\model_catalog_268.normalized.jsonl --source model_market
```

## 校验规则

导入时会检查：

- `model_id`、`model_name`、`domain`、`business_scenario`、`business_stage`、`model_capability`、`input_fields_required`、`output_fields`、`description` 等关键字段。
- 重复 `model_id`。
- `tags` 是否来自当前标签体系或现有模型资产。
- 输入/输出字段是否来自当前数据字段字典或现有模型资产字段全集。
- 官方稀疏目录会先转换为内部模型资产格式，再进入统一校验。

校验失败时脚本返回非 0 退出码，并打印最多 100 条错误。

## 字段填写约定

- 列表字段可用 `|`、`；`、`;`、`，`、`,`、`、` 分隔，也可填写 JSON 数组。
- JSON 字段应填写合法 JSON 对象，例如 `{"auc":0.82,"ks":0.45}`。
- `api_available` 支持 `true/false`、`1/0`、`yes/no`、`是/否`。
- 新增标签或字段前，应先更新 `data/knowledge/tags.json` 或对应字段字典，否则导入会报错。

## 输出结果

导入成功后输出标准 JSONL，每行一个已归一化模型资产，可继续交给 `ModelAssetRepository(raw_models=...)` 校验或后续入库流程使用。
