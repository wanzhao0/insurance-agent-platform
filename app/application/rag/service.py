from typing import Any

from app.application.knowledge.service import KnowledgeBaseService
from app.core.config import Settings
from app.domain.models import SearchResult, ToolDescriptor
from app.domain.ports import VectorStore


class RagTool:
    descriptor = ToolDescriptor(
        name="search_knowledge_base",
        description="Search tenant-scoped knowledge-base content for grounded answers.",
        input_schema={
            "type": "object",
            "properties": {
                "knowledge_base_id": {"type": "string"},
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["knowledge_base_id", "query"],
        },
    )

    def __init__(self, service: "RagService") -> None:
        self.service = service

    async def invoke(self, arguments: dict[str, Any]) -> list[SearchResult]:
        return await self.service.search(
            arguments["knowledge_base_id"], arguments["query"], arguments.get("top_k")
        )


class RagService:
    def __init__(self, knowledge_base_service: KnowledgeBaseService, vector_store: VectorStore, settings: Settings) -> None:
        self.knowledge_base_service = knowledge_base_service
        self.vector_store = vector_store
        self.settings = settings

    async def search(self, knowledge_base_id: str, query: str, top_k: int | None = None) -> list[SearchResult]:
        if self.knowledge_base_service.get(knowledge_base_id) is None:
            raise ValueError("knowledge base not found")
        return await self.vector_store.search(knowledge_base_id, query, top_k or self.settings.rag_top_k)

    def as_tool(self) -> RagTool:
        return RagTool(self)
