import asyncio
from dataclasses import dataclass, replace

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
from app.infrastructure.config_bus import build_config_bus
from app.infrastructure.model_clients.factory import build_model_client
from app.infrastructure.rate_limit.memory import InMemoryRateLimiter
from app.infrastructure.rate_limit.redis import RedisRateLimiter
from app.infrastructure.tasks.factory import build_task_queue
from app.infrastructure.object_store.factory import build_object_store
from app.infrastructure.vector.in_memory import InMemoryVectorStore
from app.infrastructure.vector.qdrant import QdrantVectorStore
from app.infrastructure.persistence.sqlalchemy import (
    SqlAlchemyAuditRepository,
    SqlAlchemyConversationRepository,
    SqlAlchemyDatabase,
    SqlAlchemyDocumentRepository,
    SqlAlchemyHandoffRepository,
    SqlAlchemyKnowledgeStore,
    SqlAlchemyConfigRepository,
    SqlAlchemyEvaluationRepository,
    SqlAlchemyTaskRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyWorkflowRepository,
)
from app.infrastructure.persistence.memory import (
    MemoryAuditRepository,
    MemoryConfigRepository,
    MemoryEvaluationRepository,
    MemoryHandoffRepository,
    MemoryTaskRepository,
    MemoryUserRepository,
    MemoryWorkflowRepository,
)
from app.plugins.base import DomainPlugin
from app.plugins.base import WorkflowStepSpec
from app.plugins.registry import load_domain_plugin


@dataclass
class AppContainer:
    settings: Settings
    auth_service: AuthService
    domain_plugin: DomainPlugin
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
    object_store: object
    user_repository: object
    config_repository: object
    task_repository: object
    evaluation_repository: object
    workflow_repository: object
    config_bus: object
    published_config_version: int | None = None
    conversation_repository: object | None = None
    audit_repository: object | None = None
    handoff_repository: object | None = None

    @property
    def logger(self):
        return get_logger("app.container")

    async def startup(self) -> None:
        await self.config_bus.start(self._handle_config_event)
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
            await asyncio.to_thread(self.database.close)
        for resource in (self.rate_limiter, self.task_queue, self.config_bus):
            close = getattr(resource, "close", None)
            if close is not None:
                await close()

    async def healthcheck(self) -> None:
        if self.database is not None:
            await asyncio.to_thread(self.database.healthcheck)
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
            domain_plugin=self.domain_plugin.plugin_id,
            domain_plugin_version=self.domain_plugin.version,
            workflow_version=self.domain_plugin.workflow_version,
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
            domain_plugin=self.domain_plugin.plugin_id,
            workflow_version=self.domain_plugin.workflow_version,
            published_config_version=self.published_config_version,
            system_prompt=self.domain_plugin.system_prompt,
            workflow_steps=[
                {
                    "name": step.name,
                    "timeout_seconds": step.timeout_seconds,
                    "on_error": step.on_error,
                }
                for step in self.domain_plugin.workflow
            ],
        )

    async def update_runtime(self, payload: RuntimeConfigUpdate) -> RuntimeConfigResponse:
        updates = payload.model_dump(exclude_unset=True)
        plugin_fields = {"system_prompt", "workflow_version", "workflow_steps"}
        setting_updates = {
            field: value for field, value in updates.items() if field not in plugin_fields
        }
        previous = {field: getattr(self.settings, field) for field in setting_updates}
        for field, value in setting_updates.items():
            setattr(self.settings, field, value)
        new_model_client = None
        try:
            new_model_client = build_model_client(self.settings)
            workflow = self.domain_plugin.workflow
            if payload.workflow_steps is not None:
                workflow = tuple(
                    WorkflowStepSpec(
                        name=step.name,
                        timeout_seconds=step.timeout_seconds,
                        on_error=step.on_error,
                    )
                    for step in payload.workflow_steps
                )
            new_plugin = replace(
                self.domain_plugin,
                system_prompt=payload.system_prompt or self.domain_plugin.system_prompt,
                workflow_version=payload.workflow_version or self.domain_plugin.workflow_version,
                workflow=workflow,
            )
            self.chat_service.replace_domain_plugin(new_plugin)
        except Exception:
            for field, value in previous.items():
                setattr(self.settings, field, value)
            if new_model_client is not None:
                close = getattr(new_model_client, "close", None)
                if close is not None:
                    await close()
            raise
        old_model_client = self.chat_service.model_client
        self.domain_plugin = new_plugin
        self.evaluation_service.domain_plugin = new_plugin
        self.chat_service.replace_model_client(new_model_client)
        self.rate_limiter.reconfigure(
            self.settings.rate_limit_requests, self.settings.rate_limit_window_seconds
        )
        close = getattr(old_model_client, "close", None)
        if close is not None:
            await close()
        return self.runtime_config()

    async def create_and_publish_runtime(
        self,
        payload: RuntimeConfigUpdate,
        actor_id: str,
        note: str = "后台运行配置更新",
    ) -> RuntimeConfigResponse:
        candidate = self.runtime_snapshot(payload)
        values = candidate.model_dump(exclude_none=True)
        version = await asyncio.to_thread(
            self.config_repository.create,
            "platform",
            "global",
            values,
            note,
            actor_id,
        )
        await self.update_runtime(candidate)
        published = await asyncio.to_thread(self.config_repository.publish, version.config_id)
        self.published_config_version = published.version if published else None
        await self.config_bus.publish(version.config_id, "platform", "global")
        return self.runtime_config()

    def runtime_snapshot(self, overrides: RuntimeConfigUpdate | None = None) -> RuntimeConfigUpdate:
        values = {
            "model_provider": self.settings.model_provider,
            "model_name": self.settings.model_name,
            "model_base_url": self.settings.model_base_url,
            "model_timeout_seconds": self.settings.model_timeout_seconds,
            "model_max_retries": self.settings.model_max_retries,
            "request_timeout_seconds": self.settings.request_timeout_seconds,
            "rag_top_k": self.settings.rag_top_k,
            "rate_limit_requests": self.settings.rate_limit_requests,
            "rate_limit_window_seconds": self.settings.rate_limit_window_seconds,
            "system_prompt": self.domain_plugin.system_prompt,
            "workflow_version": self.domain_plugin.workflow_version,
            "workflow_steps": [
                {
                    "name": step.name,
                    "timeout_seconds": step.timeout_seconds,
                    "on_error": step.on_error,
                }
                for step in self.domain_plugin.workflow
            ],
        }
        if overrides is not None:
            values.update(overrides.model_dump(exclude_unset=True))
        return RuntimeConfigUpdate.model_validate(values)

    async def publish_config(self, config_id: str) -> RuntimeConfigResponse:
        versions = await asyncio.to_thread(self.config_repository.list)
        target = next((item for item in versions if item.config_id == config_id), None)
        if target is None:
            raise ValueError("config version not found")
        if target.scope_type != "platform" or target.scope_id != "global":
            raise ValueError("tenant config publishing is not implemented for runtime settings")
        payload = RuntimeConfigUpdate.model_validate(target.values)
        await self.update_runtime(payload)
        published = await asyncio.to_thread(self.config_repository.publish, config_id)
        self.published_config_version = published.version if published else None
        await self.config_bus.publish(config_id, "platform", "global")
        return self.runtime_config()

    async def _handle_config_event(self, event: dict) -> None:
        scope_type = event.get("scope_type")
        scope_id = event.get("scope_id")
        if scope_type == "tenant" and scope_id:
            published = await asyncio.to_thread(
                self.config_repository.published,
                "tenant",
                scope_id,
            )
            if published is not None:
                from app.domain.models import TenantConfigUpdate

                await asyncio.to_thread(
                    self.knowledge_base_service.update_tenant,
                    scope_id,
                    TenantConfigUpdate.model_validate(published.values),
                )
            return
        if scope_type != "platform" or scope_id != "global":
            return
        published = await asyncio.to_thread(self.config_repository.published)
        if published is None or published.version == self.published_config_version:
            return
        await self.update_runtime(RuntimeConfigUpdate.model_validate(published.values))
        self.published_config_version = published.version


def build_container(settings: Settings) -> AppContainer:
    domain_plugin = load_domain_plugin(settings.domain_plugin)
    database = None
    persistence = None
    conversation_repository = None
    audit_repository = None
    handoff_repository = None
    user_repository = None
    config_repository = None
    task_repository = None
    evaluation_repository = None
    workflow_repository = None
    if settings.persistence_provider.lower() in {"sqlalchemy", "database", "postgres", "sqlite"}:
        database = SqlAlchemyDatabase(
            settings.database_url,
            settings.database_echo,
            settings.database_auto_create,
            settings.database_pool_size,
            settings.database_max_overflow,
        )
        document_repository = SqlAlchemyDocumentRepository(database)
        persistence = SqlAlchemyKnowledgeStore(database)
        conversation_repository = SqlAlchemyConversationRepository(database)
        audit_repository = SqlAlchemyAuditRepository(database)
        handoff_repository = SqlAlchemyHandoffRepository(database)
        user_repository = SqlAlchemyUserRepository(database)
        config_repository = SqlAlchemyConfigRepository(database)
        task_repository = SqlAlchemyTaskRepository(database)
        evaluation_repository = SqlAlchemyEvaluationRepository(database)
        workflow_repository = SqlAlchemyWorkflowRepository(database)
    else:
        document_repository = InMemoryDocumentRepository()
        audit_repository = MemoryAuditRepository()
        handoff_repository = MemoryHandoffRepository()
        user_repository = MemoryUserRepository()
        config_repository = MemoryConfigRepository()
        task_repository = MemoryTaskRepository()
        evaluation_repository = MemoryEvaluationRepository()
        workflow_repository = MemoryWorkflowRepository()
    published_config = config_repository.published()
    if published_config is not None:
        runtime_values = RuntimeConfigUpdate.model_validate(published_config.values)
        configured = runtime_values.model_dump(exclude_unset=True)
        for field, value in configured.items():
            if field in Settings.model_fields:
                setattr(settings, field, value)
        workflow = domain_plugin.workflow
        if runtime_values.workflow_steps is not None:
            workflow = tuple(
                WorkflowStepSpec(
                    name=step.name,
                    timeout_seconds=step.timeout_seconds,
                    on_error=step.on_error,
                )
                for step in runtime_values.workflow_steps
            )
        domain_plugin = replace(
            domain_plugin,
            system_prompt=runtime_values.system_prompt or domain_plugin.system_prompt,
            workflow_version=runtime_values.workflow_version or domain_plugin.workflow_version,
            workflow=workflow,
        )
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
    knowledge_base_service.seed_defaults(domain_plugin)
    embedding_client = build_embedding_client(settings)
    rag_service = RagService(knowledge_base_service, vector_store, embedding_client, settings)
    tool_registry = ToolRegistry()
    available_tools = {
        "search_knowledge_base": rag_service.as_tool(),
        "policy_lookup": PolicyLookupTool(rag_service, domain_plugin.policy_categories),
        "handoff_to_human": HandoffTool(handoff_repository),
    }
    for tool_name in domain_plugin.tool_names:
        if tool_name not in available_tools:
            raise ValueError(f"domain plugin references unknown tool: {tool_name}")
        tool_registry.register(available_tools[tool_name])
    model_client = build_model_client(settings)
    chat_service = ChatService(
        settings,
        model_client,
        knowledge_base_service,
        rag_service,
        tool_registry,
        domain_plugin,
        conversation_repository,
        workflow_repository,
    )
    evaluation_service = EvaluationService(
        chat_service,
        rag_service,
        knowledge_base_service,
        lambda: chat_service.model_client,
        domain_plugin,
        evaluation_repository,
    )
    if settings.rate_limiter_provider.lower() == "redis":
        if not settings.redis_url:
            raise ValueError("AGENT_REDIS_URL is required when AGENT_RATE_LIMITER_PROVIDER=redis")
        rate_limiter = RedisRateLimiter(
            settings.redis_url, settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
    else:
        rate_limiter = InMemoryRateLimiter(
            settings.rate_limit_requests, settings.rate_limit_window_seconds
        )
    task_queue = build_task_queue(settings)
    object_store = build_object_store(settings)
    config_bus = build_config_bus(settings.redis_url)
    auth_service = AuthService(settings, user_repository)
    auth_service.ensure_default_admin()
    return AppContainer(
        settings=settings,
        auth_service=auth_service,
        domain_plugin=domain_plugin,
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
        object_store=object_store,
        user_repository=user_repository,
        config_repository=config_repository,
        task_repository=task_repository,
        evaluation_repository=evaluation_repository,
        workflow_repository=workflow_repository,
        config_bus=config_bus,
        published_config_version=published_config.version if published_config else None,
        conversation_repository=conversation_repository,
        audit_repository=audit_repository,
        handoff_repository=handoff_repository,
    )
