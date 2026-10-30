"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "person-osint-agent"
    app_env: str = "development"
    app_debug: bool = False
    app_port: int = 8001
    demo_mode: bool = False

    # Proxycurl (LinkedIn)
    proxycurl_api_key: str = ""

    # VK
    vk_service_token: str = ""
    vk_api_version: str = "5.131"

    # Checko API
    checko_api_key: str = ""

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # extra="ignore": .env общий с другими сервисами и содержит их ключи
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
