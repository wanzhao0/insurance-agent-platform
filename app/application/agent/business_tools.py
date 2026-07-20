import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.application.rag.service import RagService
from app.domain.models import HandoffTicketResponse, SearchResult, ToolDescriptor


class PolicyLookupTool:
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
        results = await self.rag_service.search(arguments["knowledge_base_id"], arguments["query"])
        return [
            result
            for result in results
            if str(result.metadata.get("category", "")).strip().lower() in self.policy_categories
        ]


class HandoffTool:
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
