"""Embedding 客户端的最小接口约定。"""

from typing import Protocol


class EmbeddingClient(Protocol):
    """把文本转换为固定维度向量；具体供应商由基础设施层实现。"""

    dimension: int

    async def embed(self, text: str) -> list[float]: ...
