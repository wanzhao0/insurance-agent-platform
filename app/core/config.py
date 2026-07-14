from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AGENT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Insurance Agent Platform"
    app_version: str = "0.1.0"
    environment: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    admin_token: SecretStr | None = None

    model_provider: str = "mock"
    model_name: str = "insurance-agent-demo"
    model_base_url: str = "https://api.openai.com/v1"
    model_api_key: SecretStr | None = None
    model_timeout_seconds: float = 45.0
    model_max_retries: int = 2

    embedding_provider: str = "hash"
    embedding_model: str = "insurance-agent-hash-v1"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = None
    embedding_dimension: int = 1024
    vector_store_provider: str = "qdrant-local"
    vector_db_path: str = "./data/qdrant"

    request_timeout_seconds: float = 60.0
    rag_top_k: int = 4
    rag_min_score: float = 0.1
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    redis_url: str | None = None
    task_queue: str = "inline"
    max_upload_bytes: int = 10 * 1024 * 1024

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
