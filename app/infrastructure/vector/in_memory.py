import re

from app.domain.models import DocumentResponse, SearchResult
from app.domain.ports import DocumentRepository


class InMemoryVectorStore:
    """Keyword fallback with the same contract a real vector store can implement."""

    query_stopwords = (
        "请告诉我",
        "有什么",
        "请问",
        "保险产品",
        "保险",
        "产品",
        "可以",
        "推荐",
        "需要",
        "什么",
        "告诉我",
        "我",
        "你",
        "吗",
        "呢",
        "的",
    )

    def __init__(self, document_repository: DocumentRepository) -> None:
        self.document_repository = document_repository

    async def upsert(self, knowledge_base_id: str, document: DocumentResponse) -> None:
        return None

    async def search(self, knowledge_base_id: str, query: str, top_k: int) -> list[SearchResult]:
        query_terms = self._terms(query)
        candidates: list[SearchResult] = []
        for document in self.document_repository.list(knowledge_base_id):
            haystack = f"{document.title} {document.content}".lower()
            matches = sum(1 for term in query_terms if term in haystack)
            score = matches / max(len(query_terms), 1)
            if matches and score >= 0.25:
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

    @staticmethod
    def _terms(text: str) -> set[str]:
        terms: set[str] = set()
        for segment in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
            if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
                cleaned = segment
                for stopword in InMemoryVectorStore.query_stopwords:
                    cleaned = cleaned.replace(stopword, "")
                if len(cleaned) <= 4:
                    if len(cleaned) > 1:
                        terms.add(cleaned)
                else:
                    terms.update(cleaned[index : index + 2] for index in range(len(cleaned) - 1))
            elif len(segment) > 1:
                terms.add(segment)
        return terms
