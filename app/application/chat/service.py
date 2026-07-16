from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.application.agent.registry import ToolRegistry
from app.application.agent.orchestrator import AgentOrchestrator
from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.service import RagService
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models import ChatMessage, ChatRequest, SearchResult, StreamEvent
from app.domain.ports import ModelClient


SYSTEM_PROMPT = (
    "你是一个可配置的行业知识库客服 Agent。请优先依据提供的知识库上下文回答，"
    "回答前必须调用 search_knowledge_base 获取当前租户知识库证据；"
    "不要编造保单条款、金额、承保结论或法律意见。无法确认时明确说明并建议转人工。"
)


@dataclass
class ChatContext:
    request: ChatRequest
    conversation_id: str
    knowledge_base_id: str
    retrieved: list[SearchResult]
    prompt_messages: list[ChatMessage]


class ChatService:
    def __init__(
        self,
        settings: Settings,
        model_client: ModelClient,
        knowledge_base_service: KnowledgeBaseService,
        rag_service: RagService,
        tool_registry: ToolRegistry,
        conversation_repository=None,
    ) -> None:
        self.settings = settings
        self.model_client = model_client
        self.knowledge_base_service = knowledge_base_service
        self.rag_service = rag_service
        self.tool_registry = tool_registry
        self.conversation_repository = conversation_repository
        self.agent_orchestrator = AgentOrchestrator(lambda: self.model_client, tool_registry)
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

    def prepare(self, request: ChatRequest) -> ChatContext:
        knowledge_base_id = self.knowledge_base_service.resolve_knowledge_base(
            request.tenant_id, request.knowledge_base_id
        )
        return ChatContext(
            request=request,
            conversation_id=request.conversation_id,
            knowledge_base_id=knowledge_base_id,
            retrieved=[],
            prompt_messages=[ChatMessage(role="system", content=SYSTEM_PROMPT), *request.messages],
        )

    async def stream(self, context: ChatContext) -> AsyncIterator[StreamEvent]:
        state = await self.agent_orchestrator.run(context)
        if self.conversation_repository is not None:
            latest_user = next(
                (message.content for message in reversed(context.request.messages) if message.role == "user"),
                None,
            )
            self.conversation_repository.save_turn(
                context.conversation_id,
                context.request.tenant_id,
                context.knowledge_base_id,
                "user",
                latest_user,
            )
            self.conversation_repository.save_turn(
                context.conversation_id,
                context.request.tenant_id,
                context.knowledge_base_id,
                "assistant",
                state.answer,
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
