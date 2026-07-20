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
        timestamp = datetime.now(timezone.utc)
        stored = DocumentResponse(
            **document.model_dump(),
            knowledge_base_id=knowledge_base_id,
            version=(previous.version + 1 if previous else 1),
            created_at=previous.created_at if previous else timestamp,
            status=previous.status if previous else "ready",
            source_uri=previous.source_uri if previous else None,
            checksum=previous.checksum if previous else None,
            index_version=previous.index_version if previous else None,
            updated_at=timestamp,
        )
        bucket[document.document_id] = stored
        return stored

    def delete(self, knowledge_base_id: str, document_id: str) -> bool:
        bucket = self._documents.get(knowledge_base_id, {})
        return bucket.pop(document_id, None) is not None

    def update_lifecycle(
        self,
        knowledge_base_id: str,
        document_id: str,
        values: dict,
    ) -> DocumentResponse | None:
        document = self.get(knowledge_base_id, document_id)
        if document is None:
            return None
        allowed = {"status", "source_uri", "checksum", "index_version"}
        updates = {key: value for key, value in values.items() if key in allowed}
        updates["updated_at"] = datetime.now(timezone.utc)
        updated = document.model_copy(update=updates)
        self._documents[knowledge_base_id][document_id] = updated
        return updated
