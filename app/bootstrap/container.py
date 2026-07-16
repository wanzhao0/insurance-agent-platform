from dataclasses import dataclass

from app.application.agent.registry import ToolRegistry
from app.application.agent.business_tools import HandoffTool, PolicyLookupTool
from app.application.auth.service import AuthService
from app.application.chat.service import ChatService
from app.application.evaluation.service import EvaluationService
from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.service import RagService
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models import PublicConfigResponse, RuntimeConfigResponse, RuntimeConfigUpdate
from app.infrastructure.knowledge.in_memory import InMemoryDocumentRepository
from app.infrastructure.embeddings.factory import build_embedding_client
from app.infrastructure.model_clients.factory import build_model_client
from app.infrastructure.rate_limit.memory import InMemoryRateLimiter
from app.infrastructure.rate_limit.redis import RedisRateLimiter
from app.infrastructure.tasks.factory import build_task_queue
from app.infrastructure.vector.in_memory import InMemoryVectorStore
from app.infrastructure.vector.qdrant import QdrantVectorStore
from app.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyAuditRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyDatabase,
    SqlAlchemyDocumentRepository,
    SqlAlchemyHandoffRepository,
    SqlAlchemyKnowledgeStore,
)


@dataclass
class AppContainer:
    settings: Settings
    auth_service: AuthService
    document_repository: object
    vector_store: object
    database: SqlAlchemyDatabase | None
    knowledge_base_service: KnowledgeBaseService
    rag_service: RagService
    tool_registry: ToolRegistry
    chat_service: ChatService
    evaluation_service: EvaluationService
    rate_limiter: object
    task_queue: object
    conversation_repository: object | None = None
    audit_repository: object | None = None
    handoff_repository: object | None = None

    @property
    def logger(self):
        return get_logger("app.container")

    async def startup(self) -> None:
        await self.rag_service.startup()
        await self.chat_service.startup()

    async def shutdown(self) -> None:
        await self.chat_service.shutdown()
        close_vector = getattr(self.vector_store, "close", None)
        if close_vector is not None:
            await close_vector()
        close_embedding = getattr(self.rag_service.embedding_client, "close", None)
        if close_embedding is not None:
            await close_embedding()
        if self.database is not None:
            self.database.close()
        for resource in (self.rate_limiter, self.task_queue):
            close = getattr(resource, "close", None)
            if close is not None:
                await close()

    async def healthcheck(self) -> None:
        if self.database is not None:
            self.database.healthcheck()
        await self.chat_service.healthcheck()

    def public_config(self) -> PublicConfigResponse:
        return PublicConfigResponse(
            app_name=self.settings.app_name,
            app_version=self.settings.app_version,
            environment=self.settings.environment,
            model_provider=self.settings.model_provider,
            model_name=self.settings.model_name,
            rag_top_k=self.settings.rag_top_k,
            request_timeout_seconds=self.settings.request_timeout_seconds,
            available_tools=self.tool_registry.names(),
            embedding_provider=self.settings.embedding_provider,
            vector_store_provider=self.settings.vector_store_provider,
        )

    def runtime_config(self) -> RuntimeConfigResponse:
        return RuntimeConfigResponse(
            model_provider=self.settings.model_provider,
            model_name=self.settings.model_name,
            model_base_url=self.settings.model_base_url,
            model_api_key_configured=self.settings.model_api_key is not None,
            model_timeout_seconds=self.settings.model_timeout_seconds,
            model_max_retries=self.settings.model_max_retries,
            request_timeout_seconds=self.settings.request_timeout_seconds,
            rag_top_k=self.settings.rag_top_k,
            rate_limit_requests=self.settings.rate_limit_requests,
            rate_limit_window_seconds=self.settings.rate_limit_window_seconds,
            embedding_provider=self.settings.embedding_provider,
            embedding_model=self.settings.embedding_model,
            vector_store_provider=self.settings.vector_store_provider,
        )

    async def update_runtime(self, payload: RuntimeConfigUpdate) -> RuntimeConfigResponse:
        updates = payload.model_dump(exclude_unset=True)
        previous = {field: getattr(self.settings, field) for field in updates}
        for field, value in updates.items():
            setattr(self.settings, field, value)
        try:
            new_model_client = build_model_client(self.settings)
        except Exception:
            for field, value in previous.items():
                setattr(self.settings, field, value)
            raise
        old_model_client = self.chat_service.model_client
        self.chat_service.replace_model_client(new_model_client)
        self.rate_limiter.reconfigure(self.settings.rate_limit_requests, self.settings.rate_limit_window_seconds)
        close = getattr(old_model_client, "close", None)
        if close is not None:
            await close()
        return self.runtime_config()


def build_container(settings: Settings) -> AppContainer:
    database = None
    persistence = None
    conversation_repository = None
    audit_repository = None
    handoff_repository = None
    if settings.persistence_provider.lower() in {"sqlalchemy", "database", "postgres", "sqlite"}:
        database = SqlAlchemyDatabase(
            settings.database_url,
            settings.database_echo,
            settings.database_auto_create,
        )
        document_repository = SqlAlchemyDocumentRepository(database)
        persistence = SqlAlchemyKnowledgeStore(database)
        conversation_repository = SqlAlchemyConversationRepository(database)
        audit_repository = SqlAlchemyAuditRepository(database)
        handoff_repository = SqlAlchemyHandoffRepository(database)
    else:
        document_repository = InMemoryDocumentRepository()
    if settings.vector_store_provider.lower() in {"memory", "in-memory"}:
        vector_store = InMemoryVectorStore(document_repository)
    else:
        vector_store = QdrantVectorStore(
            settings.vector_db_path,
            settings.embedding_dimension,
            settings.vector_db_url,
            settings.vector_db_api_key.get_secret_value() if settings.vector_db_api_key else None,
        )
    knowledge_base_service = KnowledgeBaseService(document_repository, vector_store, persistence)
    knowledge_base_service.seed_defaults()
    embedding_client = build_embedding_client(settings)
    rag_service = RagService(knowledge_base_service, vector_store, embedding_client, settings)
    tool_registry = ToolRegistry()
    tool_registry.register(rag_service.as_tool())
    tool_registry.register(PolicyLookupTool(rag_service))
    tool_registry.register(HandoffTool(handoff_repository))
    model_client = build_model_client(settings)
    chat_service = ChatService(
        settings,
        model_client,
        knowledge_base_service,
        rag_service,
        tool_registry,
        conversation_repository,
    )
    evaluation_service = EvaluationService(
        chat_service,
        rag_service,
        knowledge_base_service,
        lambda: chat_service.model_client,
    )
    if settings.rate_limiter_provider.lower() == "redis":
        if not settings.redis_url:
            raise ValueError("AGENT_REDIS_URL is required when AGENT_RATE_LIMITER_PROVIDER=redis")
        rate_limiter = RedisRateLimiter(
            settings.redis_url, settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
    else:
        rate_limiter = InMemoryRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
    task_queue = build_task_queue(settings)
    return AppContainer(
        settings=settings,
        auth_service=AuthService(settings),
        document_repository=document_repository,
        vector_store=vector_store,
        database=database,
        knowledge_base_service=knowledge_base_service,
        rag_service=rag_service,
        tool_registry=tool_registry,
        chat_service=chat_service,
        evaluation_service=evaluation_service,
        rate_limiter=rate_limiter,
        task_queue=task_queue,
        conversation_repository=conversation_repository,
        audit_repository=audit_repository,
        handoff_repository=handoff_repository,
    )
