import asyncio

import httpx

from app.core.config import Settings


class OpenAICompatibleEmbeddingClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.dimension = settings.embedding_dimension
        self.client = httpx.AsyncClient(
            base_url=settings.embedding_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.model_timeout_seconds),
        )

    def _headers(self) -> dict[str, str]:
        if self.settings.embedding_api_key is None:
            raise RuntimeError("AGENT_EMBEDDING_API_KEY is required for the configured embedding provider")
        return {"Authorization": f"Bearer {self.settings.embedding_api_key.get_secret_value()}"}

    async def embed(self, text: str) -> list[float]:
        last_error: Exception | None = None
        for attempt in range(self.settings.model_max_retries + 1):
            try:
                response = await self.client.post(
                    "/embeddings",
                    headers=self._headers(),
                    json={"model": self.settings.embedding_model, "input": text},
                )
                response.raise_for_status()
                vector = response.json()["data"][0]["embedding"]
                if len(vector) != self.dimension:
                    self.dimension = len(vector)
                return vector
            except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
                last_error = exc
                if attempt < self.settings.model_max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise RuntimeError("embedding request failed") from last_error

    async def close(self) -> None:
        await self.client.aclose()
