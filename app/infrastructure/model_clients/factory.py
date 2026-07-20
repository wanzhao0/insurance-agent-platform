"""根据运行配置选择模型客户端实现。"""

from app.core.config import Settings
from app.domain.ports import ModelClient
from app.infrastructure.model_clients.mock import MockModelClient
from app.infrastructure.model_clients.openai_compatible import OpenAICompatibleModelClient


def build_model_client(settings: Settings) -> ModelClient:
    """新增供应商时只扩展此处分支，不改变应用层的 ``ModelClient`` 依赖。"""
    provider = settings.model_provider.lower()
    if provider == "mock":
        return MockModelClient(settings.model_name)
    if provider in {"openai", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleModelClient(settings)
    raise ValueError(f"unsupported model provider: {settings.model_provider}")
