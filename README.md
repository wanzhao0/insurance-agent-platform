# Insurance Agent Platform

一个可配置、可复用、可扩展的知识库客服 Agent 基础平台。保险是默认示例领域，核心服务通过配置、知识库、提示词、模型客户端、向量库和工具注册表支持替换到其他行业。

## 快速启动

需要 Python 3.11 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/> 可使用最小客服工作台。

打开 <http://127.0.0.1:8000/prototype/> 可体验可点击的产品原型，包含运营总览、客服工作台、知识库、文档管理、租户配置和模型工具配置。原型状态保存在当前页面内，用于先确认交互，不代表生产持久化。

默认 `AGENT_MODEL_PROVIDER=mock`，不需要 API Key。接入 OpenAI 兼容服务时，只在服务端环境变量配置：

```bash
AGENT_MODEL_PROVIDER=openai-compatible
AGENT_MODEL_BASE_URL=https://api.openai.com/v1
AGENT_MODEL_NAME=<model-name>
AGENT_MODEL_API_KEY=<server-only-secret>
```

不要把 `AGENT_MODEL_API_KEY` 放入前端、请求体、日志或仓库。

## API

- `GET /api/v1/health/live`：进程存活检查。
- `GET /api/v1/health/ready`：依赖就绪检查。
- `GET /api/v1/config/public`：不包含密钥的公开运行配置。
- `GET /api/v1/config/tenants/{tenant_id}`：租户配置、默认知识库和配置版本。
- `GET /api/v1/knowledge-bases?tenant_id=demo`：列出租户可用知识库。
- `POST /api/v1/knowledge-bases/{id}/documents`：写入文档并返回版本号。
- `POST /api/v1/knowledge-bases/{id}/search`：调用 RAG 检索接口。
- `GET /api/v1/tools`：查看已注册 Agent 工具。
- `POST /api/v1/chat/stream`：SSE 流式聊天。
- `POST /api/v1/admin/evaluations/run`：运行默认或自定义评测集，返回 RAG、引用、答案依据和安全拒答指标。

`AGENT_RAG_MIN_SCORE` 控制向量相似度的最低保留分数；默认本地 Hash Embedding 使用 `0.1`，切换真实 Embedding 后应通过评测集重新校准。
- `GET /api/v1/admin/overview`：后管概览数据。
- `GET/PATCH /api/v1/admin/runtime`：读取或更新运行时参数；API Key 只返回是否已配置。
- `GET /api/v1/admin/tenants`、`PATCH /api/v1/admin/tenants/{tenant_id}`：读取或更新租户配置。
- `GET /api/v1/admin/knowledge-bases`、`POST/PATCH /api/v1/admin/knowledge-bases/{id}`：管理知识库。
- `GET /api/v1/admin/documents`、`POST /api/v1/admin/documents/upload`、`DELETE /api/v1/admin/documents/{knowledge_base_id}/{document_id}`：查看、上传和删除文档。

SSE 事件包括 `start`、`tool_call`、`token`、`citation`、`done` 和 `error`。其中 `tool_call` 表示模型触发了已注册工具，服务端会强制注入当前租户的知识库范围。

聊天请求示例：

```json
{
  "tenant_id": "demo",
  "knowledge_base_id": "insurance-general",
  "messages": [{"role": "user", "content": "理赔需要准备什么材料？"}]
}
```

## 架构边界

```text
HTTP API
  -> Application services
       -> Domain ports (ModelClient / VectorStore / Tool / Repository)
            -> Infrastructure adapters
                 -> mock / in-memory / OpenAI-compatible
```

- `app/domain/ports.py` 定义可替换端口。
- `app/application/` 负责租户范围、RAG 编排、工作流和多智能体流程。
- `KnowledgeRetrievalAgent` 通过模型工具调用 `search_knowledge_base`，`SafetyReviewAgent` 对无证据回答做安全兜底；代理顺序由 `Workflow` 编排，可继续增加路由、理赔、产品等业务代理。
- Embedding 由 `EmbeddingClient` 抽象，默认是无需密钥的本地 Hash Embedding；可通过 `AGENT_EMBEDDING_PROVIDER=openai-compatible` 接入兼容 `/embeddings` 的服务。
- 向量库默认是本地持久化 Qdrant，数据目录由 `AGENT_VECTOR_DB_PATH` 配置；也可设为 `memory` 使用进程内适配器。生产环境可替换为远程 Qdrant、Milvus、pgvector 或其他实现。
- `InMemoryRateLimiter` 只适用于单进程开发。多实例部署时应替换为 Redis 实现。
- `AGENT_TASK_QUEUE` 保留异步任务边界，当前基础版本使用 `inline`，文档入库、重建索引等耗时任务可接入队列。
- `TaskQueue` 与 `InlineTaskQueue` 为队列替换点，生产环境可接入 Redis、Celery 或其他消息系统。
- 配置通过环境变量注入，模型 API Key 只进入后端模型客户端。
- 后管接口在 `local` 环境默认开放；部署到其他环境前设置 `AGENT_ADMIN_TOKEN`，客户端通过 `X-Admin-Token` 传递。

## 验证

```bash
pytest
ruff check app tests
```

当前默认的租户、知识库和文档元数据仍是进程内演示存储，服务重启后会恢复示例数据；生产环境应替换 `DocumentRepository` 为 Postgres 等持久化实现，并使用队列异步处理大文件解析和批量向量化。Qdrant 只负责向量索引持久化，不替代业务数据库。

### Embedding、工具调用和评测

```bash
# 使用本地零密钥模式
AGENT_EMBEDDING_PROVIDER=hash
AGENT_VECTOR_STORE_PROVIDER=qdrant-local

# 使用 OpenAI-compatible Embedding 服务（密钥只放后端环境变量）
AGENT_EMBEDDING_PROVIDER=openai-compatible
AGENT_EMBEDDING_BASE_URL=https://api.openai.com/v1
AGENT_EMBEDDING_MODEL=<embedding-model>
AGENT_EMBEDDING_API_KEY=<server-only-secret>
```

默认评测集位于 `evals/dataset.jsonl`，覆盖理赔材料、犹豫期和无依据推荐三个场景。运行：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/evaluations/run
```

也可以提交 `{"judge":"llm"}` 使用模型裁判；模型无法返回合法 JSON 时会自动回退到规则评测。评测报告包括 retrieval hit rate、citation rate、grounded answer rate、no-context precision 和 overall score。

### 文档上传

管理上传接口统一把文件解析为可检索文本，再写入文档抽象：

- Markdown、TXT、CSV、TSV、JSON：文本解析。
- PDF：按页提取文本。
- Word `.docx`：提取段落和表格。
- Excel `.xlsx`、`.xlsm`、`.xls`：按工作表和行转换为文本。

默认单文件上限为 10 MiB，可通过 `AGENT_MAX_UPLOAD_BYTES` 调整。旧式 Word `.doc`、含复杂扫描图片的 PDF、受密码保护的文件需要先转换或接入 OCR/专用解析器；系统会返回明确的格式或解析错误，不会把二进制内容直接送进模型。
