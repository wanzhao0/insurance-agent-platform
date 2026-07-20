from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.domain.models import (
    ChatMessage,
    DocumentCreate,
    DocumentResponse,
    ModelCompletion,
    SearchResult,
    ToolDescriptor,
)


class ModelClient(Protocol):
    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        tools: list[ToolDescriptor] | None = None,
    ) -> ModelCompletion: ...

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]: ...

    async def healthcheck(self) -> None: ...


class DocumentRepository(Protocol):
    def list(self, knowledge_base_id: str) -> list[DocumentResponse]: ...

    def get(self, knowledge_base_id: str, document_id: str) -> DocumentResponse | None: ...

    def add(self, knowledge_base_id: str, document: DocumentCreate) -> DocumentResponse: ...

    def delete(self, knowledge_base_id: str, document_id: str) -> bool: ...

    def update_lifecycle(
        self, knowledge_base_id: str, document_id: str, values: dict[str, Any]
    ) -> DocumentResponse | None: ...


class VectorStore(Protocol):
    async def reset(self) -> None: ...

    async def upsert(
        self, knowledge_base_id: str, document: DocumentResponse, vector: list[float]
    ) -> None: ...

    async def search(
        self, knowledge_base_id: str, vector: list[float], top_k: int
    ) -> list[SearchResult]: ...

    async def delete(self, knowledge_base_id: str, document_id: str) -> None: ...


class Tool(Protocol):
    descriptor: ToolDescriptor

    async def invoke(self, arguments: dict[str, Any]) -> Any: ...


class RateLimiter(Protocol):
    async def allow(self, key: str) -> bool: ...


class TaskQueue(Protocol):
    async def enqueue(self, task_name: str, payload: dict[str, Any]) -> str: ...


class ObjectStore(Protocol):
    async def put(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        document_id: str,
        filename: str,
        payload: bytes,
    ) -> str: ...

    async def delete(self, uri: str) -> None: ...
