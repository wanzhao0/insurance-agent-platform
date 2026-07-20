"""领域层的接口契约（ports）。

`Protocol` 可以理解为“只约定方法形状的接口”。例如 RagService 只要求 VectorStore 有
`search/upsert/delete`，并不关心实现是 Qdrant 还是内存字典。这是基础设施可替换的核心。
"""

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
    """聊天模型适配器必须实现的最小能力。"""

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
    """文档文本和生命周期状态的同步存储接口。"""

    def list(self, knowledge_base_id: str) -> list[DocumentResponse]: ...

    def get(self, knowledge_base_id: str, document_id: str) -> DocumentResponse | None: ...

    def add(self, knowledge_base_id: str, document: DocumentCreate) -> DocumentResponse: ...

    def delete(self, knowledge_base_id: str, document_id: str) -> bool: ...

    def update_lifecycle(
        self, knowledge_base_id: str, document_id: str, values: dict[str, Any]
    ) -> DocumentResponse | None: ...


class VectorStore(Protocol):
    """向量索引接口；远程向量库会产生网络等待，因此方法是异步的。"""

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
