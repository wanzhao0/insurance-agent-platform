import json
from collections.abc import Callable
from typing import Any

from app.application.agent.registry import ToolRegistry
from app.application.workflow.engine import WorkflowState
from app.domain.models import ChatMessage, SearchResult
from app.domain.ports import ModelClient


class KnowledgeRetrievalAgent:
    name = "knowledge_retrieval"

    def __init__(self, model_client_provider: Callable[[], ModelClient], tool_registry: ToolRegistry) -> None:
        self.model_client_provider = model_client_provider
        self.tool_registry = tool_registry
        self.max_rounds = 3

    async def run(self, state: WorkflowState) -> None:
        model_client = self.model_client_provider()
        messages = list(state.context.prompt_messages)
        tool_used = False
        for _ in range(self.max_rounds):
            completion = await model_client.complete(messages, tools=self.tool_registry.describe())
            if not completion.tool_calls:
                state.answer = completion.content or ""
                break

            tool_used = True
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=completion.content,
                    tool_calls=completion.tool_calls,
                )
            )
            for call in completion.tool_calls:
                state.tool_calls.append(call)
                arguments = dict(call.arguments)
                # Tenant scoping is owned by the server, never by model output.
                arguments["knowledge_base_id"] = state.context.knowledge_base_id
                result = await self.tool_registry.invoke(call.name, arguments)
                if isinstance(result, list) and all(isinstance(item, SearchResult) for item in result):
                    self._merge_results(state, result)
                messages.append(
                    ChatMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.call_id,
                        content=self._serialize_result(result),
                    )
                )
        else:
            state.answer = "模型工具调用超过最大轮次，已停止继续执行。"

        if tool_used:
            chunks: list[str] = []
            async for chunk in model_client.stream(messages):
                chunks.append(chunk)
            state.answer = "".join(chunks)
        state.messages = messages
        state.context.retrieved = state.retrieved

    @staticmethod
    def _serialize_result(result: Any) -> str:
        if isinstance(result, list):
            return json.dumps(
                [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in result],
                ensure_ascii=False,
            )
        return json.dumps(result, ensure_ascii=False, default=str)

    @staticmethod
    def _merge_results(state: WorkflowState, results: list[SearchResult]) -> None:
        existing = {item.document_id for item in state.retrieved}
        state.retrieved.extend(item for item in results if item.document_id not in existing)


class SafetyReviewAgent:
    name = "safety_review"

    async def run(self, state: WorkflowState) -> None:
        if state.retrieved:
            state.review_reason = "回答包含知识库检索证据。"
            return
        if "没有检索到" not in state.answer:
            query = next(
                (message.content or "" for message in reversed(state.context.request.messages) if message.role == "user"),
                "当前问题",
            )
            state.answer = (
                f"当前知识库没有检索到与“{query}”直接相关的内容。"
                "我无法据此确认具体条款，建议补充保单或案件信息后转人工复核。"
            )
        state.review_reason = "未找到可靠知识库证据，已阻止无依据的具体结论。"
