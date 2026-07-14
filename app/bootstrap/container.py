from dataclasses import dataclass

from app.application.agent.registry import ToolRegistry
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
from app.infrastructure.vector.in_memory import InMemoryVectorStore
from app.infrastructure.vector.qdrant import QdrantVectorStore


@dataclass
class AppContainer:
    settings: Settings
    document_repository: InMemoryDocumentRepository
    vector_store: object
    knowledge_base_service: KnowledgeBaseService
    rag_service: RagService
    tool_registry: ToolRegistry
    chat_service: ChatService
    evaluation_service: EvaluationService
    rate_limiter: InMemoryRateLimiter

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

    async def healthcheck(self) -> None:
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
    document_repository = InMemoryDocumentRepository()
    if settings.vector_store_provider.lower() in {"memory", "in-memory"}:
        vector_store = InMemoryVectorStore(document_repository)
    else:
        vector_store = QdrantVectorStore(settings.vector_db_path, settings.embedding_dimension)
    knowledge_base_service = KnowledgeBaseService(document_repository, vector_store)
    knowledge_base_service.seed_defaults()
    embedding_client = build_embedding_client(settings)
    rag_service = RagService(knowledge_base_service, vector_store, embedding_client, settings)
    tool_registry = ToolRegistry()
    tool_registry.register(rag_service.as_tool())
    model_client = build_model_client(settings)
    chat_service = ChatService(settings, model_client, knowledge_base_service, rag_service, tool_registry)
    evaluation_service = EvaluationService(
        chat_service,
        rag_service,
        knowledge_base_service,
        lambda: chat_service.model_client,
    )
    rate_limiter = InMemoryRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
    return AppContainer(
        settings=settings,
        document_repository=document_repository,
        vector_store=vector_store,
        knowledge_base_service=knowledge_base_service,
        rag_service=rag_service,
        tool_registry=tool_registry,
        chat_service=chat_service,
        evaluation_service=evaluation_service,
        rate_limiter=rate_limiter,
    )
