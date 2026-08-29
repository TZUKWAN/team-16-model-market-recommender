# OpenAPI 使用说明

## 访问方式

启动后端后，可通过以下地址访问 OpenAPI 文档：

| 地址 | 说明 |
|------|------|
| `/docs` | Swagger UI 交互式文档 |
| `/redoc` | ReDoc 文档 |
| `/openapi.json` | OpenAPI JSON Schema |

## 示例

### 本地开发访问
```
http://localhost:8000/docs
http://localhost:8000/redoc
http://localhost:8000/openapi.json
```

### Docker 环境访问
```
http://localhost:8000/docs
http://localhost:8000/redoc
http://localhost:8000/openapi.json
```

## 使用 Swagger UI

1. 打开 `http://localhost:8000/docs`
2. 展开任意端点
3. 点击 "Try it out"
4. 输入参数（如有）
5. 点击 "Execute"
6. 查看请求和响应

## 当前 API 端点

### Health

- `GET /api/v1/health` - 服务健康检查

### Demand Parsing

- `POST /api/v1/parse-demand` - 解析自然语言需求

### Recommendation

- `POST /api/v1/recommend-models` - 推荐模型

### Composition

- `POST /api/v1/recommend-composition` - 推荐组合编排

### Models

- `GET /api/v1/models/{model_id}` - 获取模型详情

### Reports

- `POST /api/v1/reports/recommendation` - 生成推荐报告

### Evaluation

- `GET /api/v1/evaluation/metrics` - 获取评估指标

## 注意事项

- 当前所有端点均返回 Mock 数据
- 将 `ENABLE_MOCK=false` 时，将尝试连接真实服务
- 所有端点统一使用 `/api/v1` 前缀
- 请求 Content-Type: `application/json`
