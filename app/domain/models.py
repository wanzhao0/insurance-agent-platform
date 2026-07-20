from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: "UserContext"


class UserContext(BaseModel):
    user_id: str
    username: str
    role: Literal["admin", "operator", "viewer"]
    tenant_ids: list[str] = Field(default_factory=list)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "operator", "viewer"] = "viewer"
    tenant_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("tenant_ids")
    @classmethod
    def validate_tenant_ids(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 100 for item in value):
            raise ValueError("tenant ids must be between 1 and 100 characters")
        return list(dict.fromkeys(value))


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Literal["admin", "operator", "viewer"] | None = None
    tenant_ids: list[str] | None = Field(default=None, max_length=100)
    enabled: bool | None = None

    @field_validator("tenant_ids")
    @classmethod
    def validate_tenant_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not item or len(item) > 100 for item in value):
            raise ValueError("tenant ids must be between 1 and 100 characters")
        return list(dict.fromkeys(value)) if value is not None else None


class UserResponse(BaseModel):
    user_id: str
    username: str
    role: Literal["admin", "operator", "viewer"]
    tenant_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class AuditLogResponse(BaseModel):
    audit_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    tenant_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationMessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None
    created_at: datetime


class ConversationResponse(BaseModel):
    conversation_id: str
    tenant_id: str
    knowledge_base_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageResponse] = Field(default_factory=list)


class HandoffTicketResponse(BaseModel):
    ticket_id: str
    tenant_id: str
    conversation_id: str | None = None
    reason: str
    status: Literal["open", "assigned", "closed"] = "open"
    created_at: datetime


class HandoffTicketUpdate(BaseModel):
    status: Literal["open", "assigned", "closed"]


class PublicConfigResponse(BaseModel):
    app_name: str
    app_version: str
    environment: str
    model_provider: str
    model_name: str
    rag_top_k: int
    request_timeout_seconds: float
    available_tools: list[str]
    embedding_provider: str
    vector_store_provider: str
    domain_plugin: str = "insurance"
    domain_plugin_version: str = "1.0.0"
    workflow_version: str = "1"


class TenantConfigResponse(BaseModel):
    tenant_id: str
    default_knowledge_base_id: str
    version: int
    enabled: bool
    settings: dict[str, Any] = Field(default_factory=dict)


class TenantSummaryResponse(BaseModel):
    tenant_id: str
    name: str
    plan: str
    default_knowledge_base_id: str
    knowledge_base_count: int
    version: int
    enabled: bool


class TenantConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    plan: str | None = Field(default=None, min_length=1, max_length=50)
    default_knowledge_base_id: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None
    settings: dict[str, Any] | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = Field(default=None, max_length=20_000)
    name: str | None = Field(default=None, max_length=100)
    tool_call_id: str | None = Field(default=None, max_length=100)
    tool_calls: list["ModelToolCall"] | None = None


class ModelToolCall(BaseModel):
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ModelCompletion(BaseModel):
    content: str | None = None
    tool_calls: list[ModelToolCall] = Field(default_factory=list)


ChatMessage.model_rebuild()
TokenResponse.model_rebuild()


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(
        default="demo", min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$"
    )
    knowledge_base_id: str | None = Field(default=None, max_length=100)
    conversation_id: str = Field(default_factory=lambda: str(uuid4()), max_length=100)
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("messages")
    @classmethod
    def require_user_message(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if not any(message.role == "user" for message in value):
            raise ValueError("messages must include at least one user message")
        return value


class DocumentCreate(BaseModel):
    document_id: str = Field(default_factory=lambda: str(uuid4()), max_length=100)
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=100_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(DocumentCreate):
    knowledge_base_id: str
    version: int
    created_at: datetime
    status: Literal["uploaded", "parsing", "parsed", "indexing", "ready", "failed"] = "ready"
    source_uri: str | None = None
    checksum: str | None = None
    index_version: str | None = None
    updated_at: datetime | None = None


class KnowledgeBaseResponse(BaseModel):
    knowledge_base_id: str
    tenant_id: str
    name: str
    description: str
    version: int
    document_count: int
    enabled: bool


class KnowledgeBaseCreate(BaseModel):
    knowledge_base_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    tenant_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    enabled: bool | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SearchResult(BaseModel):
    document_id: str
    title: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieval_sources: list[Literal["vector", "lexical", "reranked"]] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class StreamEvent(BaseModel):
    event: Literal["token", "citation", "tool_call", "message"]
    content: str | None = None
    citation: SearchResult | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class AdminDocumentCreate(DocumentCreate):
    knowledge_base_id: str = Field(min_length=1, max_length=100)


class DocumentUploadResponse(DocumentResponse):
    parser: str
    source_filename: str
    index_status: Literal["ready", "queued"] = "ready"
    task_id: str | None = None


class AdminOverviewResponse(BaseModel):
    tenant_count: int
    knowledge_base_count: int
    document_count: int
    enabled_knowledge_base_count: int


class RuntimeConfigResponse(BaseModel):
    model_provider: str
    model_name: str
    model_base_url: str
    model_api_key_configured: bool
    model_timeout_seconds: float
    model_max_retries: int
    request_timeout_seconds: float
    rag_top_k: int
    rate_limit_requests: int
    rate_limit_window_seconds: int
    embedding_provider: str
    embedding_model: str
    vector_store_provider: str
    domain_plugin: str = "insurance"
    workflow_version: str = "1"
    published_config_version: int | None = None
    system_prompt: str
    workflow_steps: list["WorkflowStepConfig"]


class WorkflowStepConfig(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    timeout_seconds: float = Field(default=45, ge=1, le=600)
    on_error: Literal["stop", "continue"] = "stop"


class RuntimeConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_provider: str | None = Field(default=None, min_length=1, max_length=50)
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_base_url: str | None = Field(default=None, min_length=1, max_length=500)
    model_timeout_seconds: float | None = Field(default=None, ge=1, le=300)
    model_max_retries: int | None = Field(default=None, ge=0, le=5)
    request_timeout_seconds: float | None = Field(default=None, ge=1, le=600)
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    rate_limit_requests: int | None = Field(default=None, ge=1, le=10000)
    rate_limit_window_seconds: int | None = Field(default=None, ge=1, le=86400)
    system_prompt: str | None = Field(default=None, min_length=20, max_length=20_000)
    workflow_version: str | None = Field(default=None, min_length=1, max_length=100)
    workflow_steps: list[WorkflowStepConfig] | None = Field(
        default=None, min_length=1, max_length=20
    )


class EvaluationCase(BaseModel):
    case_id: str
    tenant_id: str = "demo"
    knowledge_base_id: str | None = None
    query: str = Field(min_length=1, max_length=2000)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    expect_no_context: bool = False


class EvaluationRunRequest(BaseModel):
    cases: list[EvaluationCase] | None = None
    judge: Literal["rules", "llm"] = "rules"


class EvaluationCaseResult(BaseModel):
    case_id: str
    query: str
    retrieved_document_ids: list[str]
    answer: str
    retrieval_hit: bool
    citation_present: bool
    grounded: bool
    no_context_safe: bool
    judge_score: float
    judge_reason: str


class EvaluationReport(BaseModel):
    dataset_size: int
    retrieval_hit_rate: float
    citation_rate: float
    grounded_answer_rate: float
    no_context_precision: float
    overall_score: float
    cases: list[EvaluationCaseResult]


class ConfigVersionCreate(BaseModel):
    scope_type: Literal["platform", "tenant"] = "platform"
    scope_id: str = "global"
    values: dict[str, Any]
    note: str = Field(default="", max_length=500)


class ConfigVersionResponse(BaseModel):
    config_id: str
    scope_type: Literal["platform", "tenant"]
    scope_id: str
    version: int
    status: Literal["draft", "published", "archived"]
    values: dict[str, Any]
    note: str
    created_by: str
    created_at: datetime
    published_at: datetime | None = None


class TaskJobResponse(BaseModel):
    task_id: str
    task_name: str
    status: Literal["queued", "running", "succeeded", "retrying", "failed", "dead_letter"]
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowStepTrace(BaseModel):
    step: str
    status: Literal["succeeded", "failed", "skipped"]
    duration_ms: float
    error: str | None = None


class WorkflowRunResponse(BaseModel):
    run_id: str
    conversation_id: str
    tenant_id: str
    workflow_version: str
    status: Literal["succeeded", "failed"]
    steps: list[WorkflowStepTrace] = Field(default_factory=list)
    created_at: datetime


class EvaluationRunResponse(BaseModel):
    run_id: str
    judge: Literal["rules", "llm"]
    model_name: str
    plugin_id: str
    workflow_version: str
    overall_score: float
    dataset_size: int
    report: EvaluationReport
    created_at: datetime


class DomainPluginResponse(BaseModel):
    plugin_id: str
    name: str
    version: str
    workflow_version: str
    workflow_steps: list[str]
    tools: list[str]
