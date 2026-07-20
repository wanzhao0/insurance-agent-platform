"""业务工具实现。

工具描述会交给模型选择，但真正的执行始终在服务端完成；Agent 会在调用前注入当前
租户和知识库范围，不能直接信任模型提供的资源标识。
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.application.rag.service import RagService
from app.domain.models import HandoffTicketResponse, SearchResult, ToolDescriptor


class PolicyLookupTool:
    """仅检索保单和产品分类文档的领域工具。"""

    descriptor = ToolDescriptor(
        name="policy_lookup",
        description="Search policy and product documents in the current tenant knowledge base.",
        input_schema={
            "type": "object",
            "properties": {
                "knowledge_base_id": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["knowledge_base_id", "query"],
        },
    )

    def __init__(
        self, rag_service: RagService, policy_categories: frozenset[str] | None = None
    ) -> None:
        self.rag_service = rag_service
        self.policy_categories = policy_categories or frozenset({"policy", "product"})

    async def invoke(self, arguments: dict[str, Any]) -> list[SearchResult]:
        """执行 RAG 检索后按业务分类过滤，避免混入无关知识。"""
        results = await self.rag_service.search(arguments["knowledge_base_id"], arguments["query"])
        return [
            result
            for result in results
            if str(result.metadata.get("category", "")).strip().lower() in self.policy_categories
        ]


class HandoffTool:
    """在证据不足或需要人工审核时创建转人工工单。"""

    descriptor = ToolDescriptor(
        name="handoff_to_human",
        description="Create a human service ticket when evidence is missing or the customer needs manual review.",
        input_schema={
            "type": "object",
            "properties": {
                "tenant_id": {"type": "string"},
                "conversation_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["tenant_id", "reason"],
        },
    )

    def __init__(self, repository=None) -> None:
        self.repository = repository

    async def invoke(self, arguments: dict[str, Any]) -> HandoffTicketResponse:
        """优先持久化工单；无仓库时保留可用于本地演示的内存返回值。"""
        tenant_id = str(arguments["tenant_id"])
        reason = str(arguments["reason"])
        if self.repository is not None:
            return await asyncio.to_thread(
                self.repository.create,
                tenant_id,
                reason,
                arguments.get("conversation_id"),
            )
        return HandoffTicketResponse(
            ticket_id=str(uuid4()),
            tenant_id=tenant_id,
            conversation_id=arguments.get("conversation_id"),
            reason=reason,
            created_at=datetime.now(timezone.utc),
        )
