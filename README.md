# Insurance Agent Platform

一个可配置、可复用、可扩展的知识库客服 Agent 平台。保险是默认示例领域，核心代码通过租户配置、知识库、提示词、模型客户端、向量库、工具注册表和业务插件支持替换到其他行业。

## 能力范围

- Vue 3 + TypeScript + Vite + Axios + Pinia 管理后台和客服工作台。
- FastAPI 异步 API、SSE 流式聊天、请求超时、限流、结构化日志、Request ID 和 Prometheus 指标。
- Embedding + RAG：Embedding 客户端、向量库端口、Qdrant 本地/远程适配器和知识库范围隔离。
- Agent 工具调用：模型可触发知识检索、保单/产品查询和转人工工具；工具执行会被限制在当前租户范围。
- 工作流和多智能体：检索 Agent、领域 Agent、路由/安全审查节点可按配置和插件扩展。
- LLM 质量评测：规则评测、可选 LLM Judge、检索命中率、引用率、答案依据率、无上下文精确率和综合分。
- 持久化：SQLite/PostgreSQL 的 SQLAlchemy 适配器，Alembic 迁移，文档、租户、知识库、会话、审计和转人工工单可持久化。
- 高并发边界：无状态 API、Redis 限流、Redis 任务队列、独立 worker、远程 Qdrant 和多实例部署配置。
- 文档解析：Markdown、TXT、CSV、TSV、JSON、PDF、DOCX、PPTX、XLSX/XLSM/XLS。

## 本地启动

需要 Python 3.11+、Node.js 20.19+ 和 npm。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000/> 使用 FastAPI 托管的 Vue 管理台；旧版交互原型仍在 <http://127.0.0.1:8000/prototype/>。

前端独立开发时：

```bash
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173/>。Vite 默认将 `/api` 代理到 `127.0.0.1:8000`。如果后端使用其他端口，可以设置 `VITE_API_TARGET` 和 `VITE_API_BASE_URL`，例如：

```bash
VITE_API_TARGET=http://127.0.0.1:8001 \
VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1 \
npm run dev -- --port 5174
```

默认模型为 `mock`，无需 API Key。默认本地管理员为 `admin / change-me`，部署前必须通过环境变量修改密码和 JWT Secret。

## 生产启动

先配置 `.env` 中的 `AGENT_JWT_SECRET`、`AGENT_LOCAL_ADMIN_PASSWORD`、`AGENT_ADMIN_TOKEN` 和模型密钥，再启动完整依赖：

```bash
docker compose up --build
```

Compose 会启动 API、worker、PostgreSQL、Redis 和 Qdrant。API 在 <http://127.0.0.1:8000/>，文档上传在 Redis 模式下先进入任务队列，由 worker 异步完成索引。

独立运行 worker：

```bash
python -m app.worker
```

## 环境配置

关键变量：

- `AGENT_MODEL_PROVIDER=mock|openai-compatible`：模型客户端。API Key 只配置在服务端环境变量。
- `AGENT_EMBEDDING_PROVIDER=hash|openai-compatible`：Embedding 客户端。
- `AGENT_VECTOR_STORE_PROVIDER=qdrant-local|qdrant-http|memory`：向量库适配器。
- `AGENT_PERSISTENCE_PROVIDER=sqlalchemy|memory`：业务数据存储；默认 SQLite，生产使用 PostgreSQL。
- `AGENT_TASK_QUEUE=inline|redis`：文档索引任务边界。
- `AGENT_RATE_LIMITER_PROVIDER=memory|redis`：单实例或分布式限流。
- `AGENT_RAG_REBUILD_ON_STARTUP`：本地模式可开启，远程 Qdrant 多副本部署应关闭。
- `AGENT_RAG_MIN_SCORE`、`AGENT_RAG_TOP_K`：检索阈值和召回数量，应通过评测集校准。

## API

- `GET /api/v1/health/live`：进程存活检查。
- `GET /api/v1/health/ready`：数据库和模型就绪检查。
- `POST /api/v1/auth/login`、`GET /api/v1/auth/me`：管理员登录和当前用户。
- `GET /api/v1/config/public`：不包含密钥的公开运行配置。
- `GET /api/v1/config/tenants/{tenant_id}`：租户配置和默认知识库。
- `POST /api/v1/chat/stream`：SSE 流式聊天，事件包括 `start`、`tool_call`、`token`、`citation`、`done` 和 `error`。
- `GET /api/v1/conversations/{conversation_id}`：读取持久化会话。
- `POST /api/v1/knowledge-bases/{id}/search`：直接调用 RAG 检索接口。
- `GET /api/v1/tools`：查看已注册工具。
- `POST /api/v1/admin/evaluations/run`：运行规则或 LLM Judge 评测。
- `GET /api/v1/admin/overview`：后管概览数据。
- `GET/PATCH /api/v1/admin/runtime`：模型、RAG、限流等运行时参数；密钥只返回是否已配置。
- `GET/PATCH /api/v1/admin/tenants/{tenant_id}`：租户配置。
- `GET/POST/PATCH /api/v1/admin/knowledge-bases`：知识库管理。
- `GET/POST/DELETE /api/v1/admin/documents`：文档管理和多格式上传。
- `GET /api/v1/metrics`：Prometheus 指标。

管理接口支持本地管理员 JWT，也兼容配置 `AGENT_ADMIN_TOKEN` 后使用 `X-Admin-Token`。生产环境 API 无状态，鉴权、租户范围和审计边界在服务端执行。

## RAG、工具、工作流和评测

Embedding 通过 `EmbeddingClient` 端口替换，默认 Hash Embedding 不需要密钥；生产可接入 OpenAI-compatible `/embeddings`、远程 Qdrant、Milvus 或 pgvector。`KnowledgeRetrievalAgent` 必须先调用 `search_knowledge_base`，`PolicyLookupTool` 只查询 policy/product 类证据，`HandoffTool` 在缺少证据或需要人工审核时生成工单。

工作流由 Agent Orchestrator 编排检索、业务查询和安全审查节点。增加行业能力时，在 `app/application/agent/` 中实现插件并注册工具，不需要修改 HTTP 层。模型调用、向量库、队列、限流、文档仓库和业务持久化均有独立适配器边界。

默认评测集在 `evals/dataset.jsonl`，覆盖理赔材料、犹豫期和无依据产品推荐：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/evaluations/run \
  -H 'Content-Type: application/json' \
  -d '{"judge":"rules"}'
```

评测报告包括 retrieval hit rate、citation rate、grounded answer rate、no-context precision 和 overall score。LLM Judge 无法返回合法 JSON 时会回退到规则评测。

## 文档上传

上传接口会先解析为文本，再写入文档仓库和向量索引：

- Markdown、TXT、CSV、TSV、JSON：文本解析。
- PDF：按页提取文本。
- Word `.docx`：提取段落和表格。
- PowerPoint `.pptx`：提取每页文本。
- Excel `.xlsx`、`.xlsm`、`.xls`：按工作表和行转换为文本。

默认单文件上限为 10 MiB，可通过 `AGENT_MAX_UPLOAD_BYTES` 调整。旧式 Word `.doc`、扫描图片 PDF、密码保护文件需要转换格式或接入 OCR/专用解析器；系统会返回明确的格式或解析错误，不会把二进制内容直接送进模型。

## 数据库迁移

```bash
alembic upgrade head
alembic current
```

当前 `0001_initial` 是基础 schema 迁移。后续修改表结构时新增版本文件，生产环境关闭 `AGENT_DATABASE_AUTO_CREATE`，由 migrate 服务执行迁移。

## 验证

```bash
ruff check app tests
python -m compileall -q app migrations
pytest -q
cd frontend
npm run typecheck
npm run build
```

CI 会同时执行 Python 测试、Ruff 检查和 Vue 类型检查/构建。

## 架构边界

```text
Vue 3 Console / API clients
          |
      FastAPI API
          |
Application services: chat / RAG / workflow / evaluation / auth
          |
Domain ports: ModelClient / EmbeddingClient / VectorStore / Tool / Repository / TaskQueue
          |
Infrastructure: mock or OpenAI-compatible model, Qdrant, PostgreSQL, Redis, file parsers
```

保险只是默认数据和提示词。替换租户、知识库、模型、提示词和业务工具后，可以复用同一套平台实现其他行业客服 Agent。
