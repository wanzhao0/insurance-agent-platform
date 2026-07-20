# Insurance Agent Platform

一个可配置、可复用、可扩展的知识库客服 Agent 平台。保险是默认示例领域，核心代码通过租户配置、知识库、提示词、模型客户端、向量库、工具注册表和业务插件支持替换到其他行业。

## 能力范围

- Vue 3 + TypeScript + Vite + Axios + Pinia 管理后台和客服工作台。
- FastAPI 异步 API、SSE 流式聊天、请求超时、限流、结构化日志、Request ID 和 Prometheus 指标。
- Hybrid RAG：Embedding 向量召回、关键词召回、加权融合、置信度门槛、Qdrant 本地/远程适配器和知识库范围隔离。
- Agent 工具调用：模型可触发知识检索、保单/产品查询和转人工工具；工具执行会被限制在当前租户范围。
- 声明式工作流和多智能体：检索 Agent、安全审查 Agent 的顺序、超时和失败策略可版本化发布，每次运行保留步骤级轨迹。
- LLM 质量评测：规则评测、可选 LLM Judge、检索命中率、引用率、答案依据率、无上下文精确率和历史报告。
- 领域插件：默认保险插件统一提供提示词、工作流、工具白名单、默认租户/知识和评测集，HTTP 与基础设施层不依赖保险规则。
- 治理与权限：用户、Admin/Operator/Viewer RBAC、租户授权、配置完整快照、历史回滚、审计日志和转人工工单。
- 持久化：SQLite/PostgreSQL 的 SQLAlchemy 适配器，Alembic 迁移，文档生命周期、配置、任务、会话、评测和工作流运行均可持久化。
- 高并发边界：无状态 API、阻塞存储线程卸载、数据库连接池、Redis 限流、Redis Streams 消费组/延迟重试/死信、独立 worker 和多实例配置广播。
- 对象存储：本地文件系统以及 S3/MinIO 适配器，原文件与解析文本分离保存。
- 可观测性：结构化日志、Request ID、低基数 Prometheus 指标、工作流/RAG 延迟和可选 OpenTelemetry OTLP 链路。
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
- `AGENT_DOMAIN_PLUGIN=insurance`：选择领域插件；新增行业只需注册新的 `DomainPlugin`。
- `AGENT_OBJECT_STORE_PROVIDER=local|s3|minio`：原文件对象存储；S3/MinIO 凭据只从服务端环境变量读取。
- `AGENT_RAG_REBUILD_ON_STARTUP`：本地模式可开启，远程 Qdrant 多副本部署应关闭。
- `AGENT_RAG_MIN_SCORE`、`AGENT_RAG_TOP_K`、`AGENT_RAG_VECTOR_WEIGHT`、`AGENT_RAG_LEXICAL_WEIGHT`：混合检索参数，应通过评测集校准。
- `AGENT_OTEL_ENABLED`、`AGENT_OTEL_EXPORTER_OTLP_ENDPOINT`：开启 OTLP HTTP trace 导出。

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
- `GET /api/v1/admin/evaluations`：读取持久化评测历史。
- `GET /api/v1/admin/overview`：后管概览数据。
- `GET/PATCH /api/v1/admin/runtime`：发布模型、RAG、限流、提示词和声明式工作流完整快照；密钥只返回是否已配置。
- `GET/POST/PATCH /api/v1/admin/users`：用户、角色和租户授权管理。
- `GET/POST /api/v1/admin/config-versions`：配置版本列表、草稿和历史版本发布。
- `GET /api/v1/admin/tasks`、`GET /api/v1/admin/workflow-runs`：后台任务和步骤级工作流轨迹。
- `GET /api/v1/admin/audit-logs`、`GET/PATCH /api/v1/admin/handoffs`：审计和转人工工单。
- `GET/PATCH /api/v1/admin/tenants/{tenant_id}`：租户配置。
- `GET/POST/PATCH /api/v1/admin/knowledge-bases`：知识库管理。
- `GET/POST/DELETE /api/v1/admin/documents`：文档管理和多格式上传。
- `GET /api/v1/metrics`：Prometheus 指标。

管理接口支持本地管理员 JWT，也兼容配置 `AGENT_ADMIN_TOKEN` 后使用 `X-Admin-Token`。生产环境 API 无状态，鉴权、租户范围和审计边界在服务端执行。

## RAG、工具、工作流和评测

Embedding 通过 `EmbeddingClient` 端口替换，默认 Hash Embedding 不需要密钥；生产可接入 OpenAI-compatible `/embeddings`、远程 Qdrant、Milvus 或 pgvector。`KnowledgeRetrievalAgent` 必须先调用 `search_knowledge_base`，`PolicyLookupTool` 只查询 policy/product 类证据，`HandoffTool` 在缺少证据或需要人工审核时生成工单。

工作流由 Agent Orchestrator 按已发布配置编排检索和安全审查节点。增加行业能力时，在 `app/plugins/` 注册领域插件，并通过工具适配器提供业务动作，不需要修改 HTTP 层。模型调用、Embedding、向量库、对象存储、队列、限流和持久化均有独立适配器边界。

默认评测集在 `evals/dataset.jsonl`，覆盖理赔材料、犹豫期和无依据产品推荐：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/evaluations/run \
  -H 'Content-Type: application/json' \
  -d '{"judge":"rules"}'
```

评测报告包括 retrieval hit rate、citation rate、grounded answer rate、no-context precision 和 overall score。LLM Judge 无法返回合法 JSON 时会回退到规则评测。

## 文档上传

上传接口以 1 MiB 分段限制请求体，保存原文件并计算 SHA-256，然后解析文本、更新生命周期并进入索引：

- Markdown、TXT、CSV、TSV、JSON：文本解析。
- PDF：按页提取文本。
- Word `.docx`：提取段落和表格。
- PowerPoint `.pptx`：提取每页文本。
- Excel `.xlsx`、`.xlsm`、`.xls`：按工作表和行转换为文本。

状态依次为 `parsed → indexing → ready`，失败时记录为 `failed`；每个文档保留 `source_uri`、`checksum` 和 `index_version`。默认单文件上限为 10 MiB，解析文本上限为 100,000 字符。旧式 Word `.doc`、扫描图片 PDF、密码保护文件需要转换格式或接入 OCR/专用解析器；系统会返回明确的格式或解析错误，不会把二进制内容直接送进模型。

## 数据库迁移

```bash
alembic upgrade head
alembic current
```

`0001_initial` 是基础 schema，`0002_platform_governance` 增加用户、配置版本、任务、评测、工作流运行和文档生命周期。生产环境关闭 `AGENT_DATABASE_AUTO_CREATE`，由 migrate 服务执行迁移。

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
Domain plugin + versioned config
          |
Application services: chat / hybrid RAG / workflow / evaluation / auth
          |
Domain ports: ModelClient / EmbeddingClient / VectorStore / Tool / Repository / TaskQueue
          |
Infrastructure: model / Qdrant / PostgreSQL / Redis Streams / S3 / file parsers
```

保险只是默认数据和提示词。替换租户、知识库、模型、提示词和业务工具后，可以复用同一套平台实现其他行业客服 Agent。
