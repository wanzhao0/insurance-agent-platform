from app.domain.models import DocumentResponse, SearchResult
from app.domain.ports import DocumentRepository


class InMemoryVectorStore:
    """In-process vector fallback for tests and minimal deployments."""

    def __init__(self, document_repository: DocumentRepository) -> None:
        self.document_repository = document_repository
        self._vectors: dict[tuple[str, str], list[float]] = {}
        self._documents: dict[tuple[str, str], DocumentResponse] = {}

    async def reset(self) -> None:
        self._vectors.clear()
        self._documents.clear()

    async def upsert(
        self, knowledge_base_id: str, document: DocumentResponse, vector: list[float]
    ) -> None:
        self._vectors[(knowledge_base_id, document.document_id)] = vector
        self._documents[(knowledge_base_id, document.document_id)] = document

    async def search(
        self, knowledge_base_id: str, vector: list[float], top_k: int
    ) -> list[SearchResult]:
        candidates: list[SearchResult] = []
        for (stored_knowledge_base_id, _), document in self._documents.items():
            if stored_knowledge_base_id != knowledge_base_id:
                continue
            stored = self._vectors[(knowledge_base_id, document.document_id)]
            score = sum(left * right for left, right in zip(vector, stored, strict=False))
            if score > 0:
                candidates.append(
                    SearchResult(
                        document_id=document.document_id,
                        title=document.title,
                        content=document.content,
                        score=round(score, 4),
                        metadata=document.metadata,
                    )
                )
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:top_k]

    async def delete(self, knowledge_base_id: str, document_id: str) -> None:
        for key in [
            key
            for key in self._vectors
            if key[0] == knowledge_base_id
            and (key[1] == document_id or key[1].startswith(f"{document_id}:chunk-"))
        ]:
            self._vectors.pop(key, None)
            self._documents.pop(key, None)
