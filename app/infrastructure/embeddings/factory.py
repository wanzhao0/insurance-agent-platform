"""根据配置构建 Embedding 客户端。"""

from app.application.rag.embedding import EmbeddingClient
from app.core.config import Settings
from app.infrastructure.embeddings.hash import HashEmbeddingClient
from app.infrastructure.embeddings.openai_compatible import OpenAICompatibleEmbeddingClient


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    """本地默认使用确定性的 hash 向量；生产可切换到兼容 OpenAI 的服务。"""
    provider = settings.embedding_provider.lower()
    if provider in {"hash", "local", "mock"}:
        return HashEmbeddingClient(settings.embedding_dimension)
    if provider in {"openai", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleEmbeddingClient(settings)
    raise ValueError(f"unsupported embedding provider: {settings.embedding_provider}")
