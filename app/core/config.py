from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
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
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:5174",
            "http://localhost:5174",
        ]
    )
    admin_token: SecretStr | None = None
    domain_plugin: str = "insurance"

    persistence_provider: str = "sqlalchemy"
    database_url: str = "sqlite:///./data/agent.db"
    database_echo: bool = False
    database_auto_create: bool = True
    database_pool_size: int = 10
    database_max_overflow: int = 20
    jwt_secret: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 480
    local_admin_username: str = "admin"
    local_admin_password: SecretStr = SecretStr("change-me")

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
    vector_db_url: str | None = None
    vector_db_api_key: SecretStr | None = None

    request_timeout_seconds: float = 60.0
    rag_top_k: int = 4
    rag_min_score: float = 0.1
    rag_rebuild_on_startup: bool = True
    rag_vector_weight: float = 0.7
    rag_lexical_weight: float = 0.3
    rag_index_version: str = "v1"
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    redis_url: str | None = None
    task_queue: str = "inline"
    task_max_attempts: int = 3
    task_retry_delay_seconds: int = 5
    worker_metrics_port: int = 9101
    rate_limiter_provider: str = "memory"
    max_upload_bytes: int = 10 * 1024 * 1024
    object_store_provider: str = "local"
    object_store_path: str = "./data/objects"
    object_store_bucket: str = "agent-documents"
    object_store_endpoint_url: str | None = None
    object_store_region: str = "us-east-1"
    object_store_access_key: SecretStr | None = None
    object_store_secret_key: SecretStr | None = None
    metrics_enabled: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "insurance-agent-platform"
    otel_exporter_otlp_endpoint: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("rag_vector_weight", "rag_lexical_weight")
    @classmethod
    def validate_rag_weight(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("RAG weights must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment.lower() == "production":
            if self.jwt_secret is None:
                raise ValueError("AGENT_JWT_SECRET is required in production")
            if self.local_admin_password.get_secret_value() == "change-me":
                raise ValueError("AGENT_LOCAL_ADMIN_PASSWORD must be changed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
