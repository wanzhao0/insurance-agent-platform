from app.core.config import Settings
from app.domain.ports import ModelClient
from app.infrastructure.model_clients.mock import MockModelClient
from app.infrastructure.model_clients.openai_compatible import OpenAICompatibleModelClient


def build_model_client(settings: Settings) -> ModelClient:
    provider = settings.model_provider.lower()
    if provider == "mock":
        return MockModelClient(settings.model_name)
    if provider in {"openai", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleModelClient(settings)
    raise ValueError(f"unsupported model provider: {settings.model_provider}")
