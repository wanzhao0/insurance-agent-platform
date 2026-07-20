import asyncio
import re
import time
from typing import Any

from app.application.knowledge.service import KnowledgeBaseService
from app.application.rag.embedding import EmbeddingClient
from app.core.config import Settings
from app.core.metrics import RAG_DURATION, RAG_SEARCHES
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
    generic_query_phrases = (
        "有什么",
        "请问",
        "请告诉我",
        "可以",
        "保险产品",
        "保险",
        "产品",
        "推荐的",
        "推荐",
        "一下",
        "相关",
        "信息",
    )

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

    async def search(
        self, knowledge_base_id: str, query: str, top_k: int | None = None
    ) -> list[SearchResult]:
        started = time.perf_counter()
        if self.knowledge_base_service.get(knowledge_base_id) is None:
            raise ValueError("knowledge base not found")
        limit = top_k or self.settings.rag_top_k
        vector = await self.embedding_client.embed(query)
        vector_results = await self.vector_store.search(
            knowledge_base_id, vector, max(limit * 3, limit)
        )
        documents = await asyncio.to_thread(
            self.knowledge_base_service.document_repository.list, knowledge_base_id
        )
        lexical_scores = {
            document.document_id: self._lexical_score(
                query, f"{document.title}\n{document.content}"
            )
            for document in documents
        }
        by_document = {document.document_id: document for document in documents}
        grouped: dict[str, SearchResult] = {}
        for result in vector_results:
            source_id = str(
                result.metadata.get("source_document_id", result.document_id.split(":chunk-")[0])
            )
            lexical = lexical_scores.get(source_id, 0.0)
            if lexical == 0 and result.score < max(self.settings.rag_min_score, 0.55):
                continue
            combined = (
                result.score * self.settings.rag_vector_weight
                + lexical * self.settings.rag_lexical_weight
            )
            if combined < self.settings.rag_min_score:
                continue
            result.document_id = source_id
            result.score = round(combined, 4)
            result.retrieval_sources = ["vector"] + (["lexical"] if lexical else [])
            existing = grouped.get(source_id)
            if existing is None:
                grouped[source_id] = result
            elif result.content not in existing.content:
                existing.content = f"{existing.content}\n\n{result.content}"
                existing.score = max(existing.score, result.score)

        for document_id, lexical in lexical_scores.items():
            if lexical <= 0:
                continue
            score = round(lexical * self.settings.rag_lexical_weight, 4)
            if score < self.settings.rag_min_score:
                continue
            existing = grouped.get(document_id)
            if existing is not None:
                if "lexical" not in existing.retrieval_sources:
                    existing.retrieval_sources.append("lexical")
                continue
            document = by_document[document_id]
            grouped[document_id] = SearchResult(
                document_id=document.document_id,
                title=document.title,
                content=document.content,
                score=score,
                metadata=document.metadata,
                retrieval_sources=["lexical"],
            )

        results = sorted(grouped.values(), key=lambda item: item.score, reverse=True)[:limit]
        RAG_SEARCHES.labels("hit" if results else "miss").inc()
        RAG_DURATION.observe(time.perf_counter() - started)
        return results

    async def index_document(self, document: DocumentResponse) -> None:
        await asyncio.to_thread(
            self.knowledge_base_service.document_repository.update_lifecycle,
            document.knowledge_base_id,
            document.document_id,
            {"status": "indexing"},
        )
        try:
            chunks = self._chunks(document.content)
            indexed_chunks: list[tuple[DocumentResponse, list[float]]] = []
            for index, content in enumerate(chunks):
                chunk_id = (
                    document.document_id
                    if len(chunks) == 1
                    else f"{document.document_id}:chunk-{index}"
                )
                chunk = document.model_copy(
                    update={
                        "document_id": chunk_id,
                        "content": content,
                        "metadata": {
                            **document.metadata,
                            "source_document_id": document.document_id,
                            "chunk_index": index,
                            "index_version": self.index_version,
                        },
                    }
                )
                vector = await self.embedding_client.embed(f"{document.title}\n{content}")
                indexed_chunks.append((chunk, vector))

            # Keep the previous index intact if embedding fails before this point.
            await self.vector_store.delete(document.knowledge_base_id, document.document_id)
            for chunk, vector in indexed_chunks:
                await self.vector_store.upsert(document.knowledge_base_id, chunk, vector)
        except Exception:
            await asyncio.to_thread(
                self.knowledge_base_service.document_repository.update_lifecycle,
                document.knowledge_base_id,
                document.document_id,
                {"status": "failed"},
            )
            raise
        await asyncio.to_thread(
            self.knowledge_base_service.document_repository.update_lifecycle,
            document.knowledge_base_id,
            document.document_id,
            {"status": "ready", "index_version": self.index_version},
        )

    @property
    def index_version(self) -> str:
        return f"{self.settings.rag_index_version}:{self.settings.embedding_model}"

    @classmethod
    def _lexical_score(cls, query: str, content: str) -> float:
        normalized = query.lower()
        for phrase in cls.generic_query_phrases:
            normalized = normalized.replace(phrase, "")
        query_tokens = cls._tokens(normalized)
        if not query_tokens:
            return 0.0
        content_tokens = cls._tokens(content.lower())
        matched = sum(token in content_tokens for token in query_tokens)
        return matched / len(query_tokens)

    @staticmethod
    def _tokens(value: str) -> set[str]:
        latin = set(re.findall(r"[a-z0-9]{2,}", value))
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", value)
        chinese = {
            run[index : index + 2] for run in chinese_runs for index in range(max(0, len(run) - 1))
        }
        return latin | chinese

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
        if not self.settings.rag_rebuild_on_startup:
            return
        reset = getattr(self.vector_store, "reset", None)
        if reset is not None:
            await reset()
        documents = await asyncio.to_thread(self.knowledge_base_service.list_all_documents)
        for document in documents:
            await self.index_document(document)

    async def delete_document(self, knowledge_base_id: str, document_id: str) -> None:
        await self.vector_store.delete(knowledge_base_id, document_id)

    def as_tool(self) -> RagTool:
        return RagTool(self)
