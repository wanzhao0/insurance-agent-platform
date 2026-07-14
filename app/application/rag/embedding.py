from typing import Protocol


class EmbeddingClient(Protocol):
    dimension: int

    async def embed(self, text: str) -> list[float]: ...
