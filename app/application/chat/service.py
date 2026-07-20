"""聊天用例：把 HTTP 请求转换为可执行工作流，并将结果以 SSE 事件输出。"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
import asyncio

from app.application.agent.registry import ToolRegistry
from app.application.agent.orchestrator import AgentOrchestrator
from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.service import RagService
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models import ChatMessage, ChatRequest, SearchResult, StreamEvent
from app.domain.ports import ModelClient
from app.plugins.base import DomainPlugin
from app.application.workflow.engine import WorkflowExecutionError


@dataclass
class ChatContext:
    """一次聊天在工作流中共享的输入。

    `knowledge_base_id` 在进入工作流前已经按租户校验，因此后续 Agent 不需要再次相信客户端传值。
    """

    request: ChatRequest
    conversation_id: str
    knowledge_base_id: str
    retrieved: list[SearchResult]
    prompt_messages: list[ChatMessage]
    persist_conversation: bool


class ChatService:
    """协调知识库范围、提示词、工作流、会话持久化和 SSE 输出。

    这个类不直接知道 Qdrant 或 SQLAlchemy 的细节，依赖在启动时由 AppContainer 注入。
    """

    def __init__(
        self,
        settings: Settings,
        model_client: ModelClient,
        knowledge_base_service: KnowledgeBaseService,
        rag_service: RagService,
        tool_registry: ToolRegistry,
        domain_plugin: DomainPlugin,
        conversation_repository=None,
        workflow_repository=None,
    ) -> None:
        self.settings = settings
        self.model_client = model_client
        self.knowledge_base_service = knowledge_base_service
        self.rag_service = rag_service
        self.tool_registry = tool_registry
        self.domain_plugin = domain_plugin
        self.conversation_repository = conversation_repository
        self.workflow_repository = workflow_repository
        self.agent_orchestrator = AgentOrchestrator(
            lambda: self.model_client,
            tool_registry,
            domain_plugin.workflow,
        )
        self.logger = get_logger(__name__)

    async def startup(self) -> None:
        return None

    async def shutdown(self) -> None:
        close = getattr(self.model_client, "close", None)
        if close is not None:
            await close()

    async def healthcheck(self) -> None:
        await self.model_client.healthcheck()

    def replace_model_client(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def replace_domain_plugin(self, domain_plugin: DomainPlugin) -> None:
        orchestrator = AgentOrchestrator(
            lambda: self.model_client,
            self.tool_registry,
            domain_plugin.workflow,
        )
        self.domain_plugin = domain_plugin
        self.agent_orchestrator = orchestrator

    def prepare(self, request: ChatRequest, *, persist_conversation: bool = True) -> ChatContext:
        """在调用模型前锁定租户可访问的知识库，并追加领域系统提示词。"""
        knowledge_base_id = self.knowledge_base_service.resolve_knowledge_base(
            request.tenant_id, request.knowledge_base_id
        )
        return ChatContext(
            request=request,
            conversation_id=request.conversation_id,
            knowledge_base_id=knowledge_base_id,
            retrieved=[],
            prompt_messages=[
                ChatMessage(role="system", content=self.domain_plugin.system_prompt),
                *request.messages,
            ],
            persist_conversation=persist_conversation,
        )

    async def stream(self, context: ChatContext) -> AsyncIterator[StreamEvent]:
        """运行工作流并逐个产生 SSE 事件。

        API 层会把这里的 `StreamEvent` 序列化成 SSE。即使当前模型一次返回完整回答，仍按小片段
        输出，以保持流式协议与真实流式模型兼容。
        """
        try:
            state = await self.agent_orchestrator.run(context)
        except WorkflowExecutionError as exc:
            if self.workflow_repository is not None and context.persist_conversation:
                await asyncio.to_thread(
                    self.workflow_repository.record,
                    context.conversation_id,
                    context.request.tenant_id,
                    self.domain_plugin.workflow_version,
                    "failed",
                    [trace.model_dump(mode="json") for trace in exc.state.traces],
                )
            raise exc.cause from exc
        if self.conversation_repository is not None and context.persist_conversation:
            latest_user = next(
                (
                    message.content
                    for message in reversed(context.request.messages)
                    if message.role == "user"
                ),
                None,
            )
            # SQLAlchemy 仓库是同步实现；放到线程池避免占住 FastAPI 的异步事件循环。
            await asyncio.to_thread(
                self.conversation_repository.save_turn,
                context.conversation_id,
                context.request.tenant_id,
                context.knowledge_base_id,
                "user",
                latest_user,
            )
            await asyncio.to_thread(
                self.conversation_repository.save_turn,
                context.conversation_id,
                context.request.tenant_id,
                context.knowledge_base_id,
                "assistant",
                state.answer,
            )
        if self.workflow_repository is not None and context.persist_conversation:
            await asyncio.to_thread(
                self.workflow_repository.record,
                context.conversation_id,
                context.request.tenant_id,
                self.domain_plugin.workflow_version,
                "succeeded",
                [trace.model_dump(mode="json") for trace in state.traces],
            )
        for call in state.tool_calls:
            yield StreamEvent(event="tool_call", tool_name=call.name, tool_call_id=call.call_id)
        emitted = 0
        answer = state.answer
        for index in range(0, len(answer), 12):
            token = answer[index : index + 12]
            emitted += 1
            yield StreamEvent(event="token", content=token)
        for result in state.retrieved:
            yield StreamEvent(event="citation", citation=result)
        self.logger.info(
            "chat_completed",
            extra={"conversation_id": context.conversation_id, "token_chunks": emitted},
        )
