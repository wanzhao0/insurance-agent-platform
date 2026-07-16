from typing import Any

from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.embedding import EmbeddingClient
from app.core.config import Settings
from app.domain.models import DocumentResponse, SearchResult, ToolDescriptor
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
    chunk_size = 600
    chunk_overlap = 80
    def __init__(
        self,
        knowledge_base_service: KnowledgeBaseService,
        vector_store: VectorStore,
        embedding_client: EmbeddingClient,
        settings: Settings,
    ) -> None:
        self.knowledge_base_service = knowledge_base_service
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.settings = settings

    async def search(self, knowledge_base_id: str, query: str, top_k: int | None = None) -> list[SearchResult]:
        if self.knowledge_base_service.get(knowledge_base_id) is None:
            raise ValueError("knowledge base not found")
        vector = await self.embedding_client.embed(query)
        results = await self.vector_store.search(knowledge_base_id, vector, top_k or self.settings.rag_top_k)
        grouped: dict[str, SearchResult] = {}
        for result in results:
            if result.score < self.settings.rag_min_score:
                continue
            existing = grouped.get(result.document_id)
            if existing is None:
                grouped[result.document_id] = result
            elif result.content not in existing.content:
                existing.content = f"{existing.content}\n\n{result.content}"
                existing.score = max(existing.score, result.score)
        return list(grouped.values())[: top_k or self.settings.rag_top_k]

    async def index_document(self, document: DocumentResponse) -> None:
        chunks = self._chunks(document.content)
        for index, content in enumerate(chunks):
            chunk_id = document.document_id if len(chunks) == 1 else f"{document.document_id}:chunk-{index}"
            chunk = document.model_copy(
                update={
                    "document_id": chunk_id,
                    "content": content,
                    "metadata": {
                        **document.metadata,
                        "source_document_id": document.document_id,
                        "chunk_index": index,
                    },
                }
            )
            vector = await self.embedding_client.embed(f"{document.title}\n{content}")
            await self.vector_store.upsert(document.knowledge_base_id, chunk, vector)

    @classmethod
    def _chunks(cls, content: str) -> list[str]:
        if len(content) <= cls.chunk_size:
            return [content]
        chunks: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + cls.chunk_size, len(content))
            if end < len(content):
                boundary = max(content.rfind("\n", start, end), content.rfind("。", start, end))
                if boundary > start + cls.chunk_size // 2:
                    end = boundary + 1
            chunks.append(content[start:end].strip())
            if end >= len(content):
                break
            start = max(end - cls.chunk_overlap, start + 1)
        return [chunk for chunk in chunks if chunk]

    async def startup(self) -> None:
        reset = getattr(self.vector_store, "reset", None)
        if self.settings.rag_rebuild_on_startup and reset is not None:
            await reset()
        for document in self.knowledge_base_service.list_all_documents():
            await self.index_document(document)

    async def delete_document(self, knowledge_base_id: str, document_id: str) -> None:
        await self.vector_store.delete(knowledge_base_id, document_id)

    def as_tool(self) -> RagTool:
        return RagTool(self)
