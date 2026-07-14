from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.application.agent.registry import ToolRegistry
from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.service import RagService
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.models import ChatMessage, ChatRequest, SearchResult, StreamEvent
from app.domain.ports import ModelClient


SYSTEM_PROMPT = (
    "你是一个可配置的行业知识库客服 Agent。请优先依据提供的知识库上下文回答，"
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
    ) -> None:
        self.settings = settings
        self.model_client = model_client
        self.knowledge_base_service = knowledge_base_service
        self.rag_service = rag_service
        self.tool_registry = tool_registry
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
        latest_user_message = next(
            message.content for message in reversed(context.request.messages) if message.role == "user"
        )
        context.retrieved = await self.rag_service.search(
            context.knowledge_base_id, latest_user_message, self.settings.rag_top_k
        )
        if context.retrieved:
            citations = "\n\n".join(
                f"[{index}] {result.title}\n{result.content}" for index, result in enumerate(context.retrieved, 1)
            )
            context.prompt_messages.insert(
                1,
                ChatMessage(role="system", content=f"知识库上下文（仅供参考）：\n{citations}"),
            )
        else:
            context.prompt_messages.insert(1, ChatMessage(role="system", content="本次检索没有找到相关知识库内容。"))

        emitted = 0
        async for token in self.model_client.stream(context.prompt_messages):
            emitted += 1
            yield StreamEvent(event="token", content=token)
        for result in context.retrieved:
            yield StreamEvent(event="citation", citation=result)
        self.logger.info(
            "chat_completed",
            extra={"conversation_id": context.conversation_id, "token_chunks": emitted},
        )
