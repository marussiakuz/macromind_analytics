"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field, SecretStr


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "osint-agent"
    app_env: str = "development"
    app_debug: bool = False
    app_port: int = 8000
    demo_mode: bool = False

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "osint"
    postgres_user: str = "osint"
    postgres_password: str = "changeme"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # VK API
    vk_service_token: str = ""
    vk_api_version: str = "5.131"

    # External APIs (optional)
    checko_api_key: SecretStr = SecretStr("")
    spark_api_key: str = ""
    kontur_api_key: str = ""
    proxycurl_api_key: str = ""
    tavily_api_key: str = ""
    brave_api_key: str = ""
    crunchbase_api_key: str = ""
    shodan_api_key: str = ""  # Optional — Shodan не падает без ключа
    # Market module (plan §7)
    yandex_api_key: SecretStr = SecretStr("")
    yandex_folder_id: str = ""
    openalex_api_key: SecretStr = SecretStr("")

    # Knowledge / RAG (Task2 §13)
    knowledge_database_url: str = ""
    knowledge_objects_root: str = "data/knowledge-objects"
    knowledge_internal_base_url: str = ""
    knowledge_internal_token: str = ""
    knowledge_user_access: str = ""
    embedding_base_url: str = "http://127.0.0.1:8091"
    embedding_api_token: str = ""
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_revision: str = "main"
    embedding_dimension: int = 1024
    knowledge_schema_version: str = "0003"
    knowledge_search_profile: str = "v1"
    knowledge_job_deadline_seconds: int = 1800
    knowledge_max_parallel_jobs: int = 1

    # Sanctions
    sanctions_update_cron: str = "0 3 * * *"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Rate limiting
    rate_limit_enabled: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
