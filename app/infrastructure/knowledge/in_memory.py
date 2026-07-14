from datetime import datetime, timezone

from app.domain.models import DocumentCreate, DocumentResponse


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, dict[str, DocumentResponse]] = {}

    def list(self, knowledge_base_id: str) -> list[DocumentResponse]:
        return list(self._documents.get(knowledge_base_id, {}).values())

    def get(self, knowledge_base_id: str, document_id: str) -> DocumentResponse | None:
        return self._documents.get(knowledge_base_id, {}).get(document_id)

    def add(self, knowledge_base_id: str, document: DocumentCreate) -> DocumentResponse:
        bucket = self._documents.setdefault(knowledge_base_id, {})
        previous = bucket.get(document.document_id)
        stored = DocumentResponse(
            **document.model_dump(),
            knowledge_base_id=knowledge_base_id,
            version=(previous.version + 1 if previous else 1),
            created_at=datetime.now(timezone.utc),
        )
        bucket[document.document_id] = stored
        return stored

    def delete(self, knowledge_base_id: str, document_id: str) -> bool:
        bucket = self._documents.get(knowledge_base_id, {})
        return bucket.pop(document_id, None) is not None
