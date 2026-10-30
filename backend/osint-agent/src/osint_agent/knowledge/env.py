"""Resolve knowledge env from pydantic Settings (os.environ wins)."""

from __future__ import annotations

import os


def apply_knowledge_env() -> dict[str, str]:
    """Copy Settings → os.environ for knowledge keys if not already set.

    pydantic-settings loads .env into Settings but does not export to os.environ.
    """
    try:
        from osint_agent.config import settings
    except Exception:  # noqa: BLE001
        return {}
    mapping = {
        "KNOWLEDGE_DATABASE_URL": getattr(settings, "knowledge_database_url", ""),
        "KNOWLEDGE_OBJECTS_ROOT": getattr(settings, "knowledge_objects_root", ""),
        "KNOWLEDGE_INTERNAL_BASE_URL": getattr(settings, "knowledge_internal_base_url", ""),
        "KNOWLEDGE_INTERNAL_TOKEN": getattr(settings, "knowledge_internal_token", ""),
        "KNOWLEDGE_USER_ACCESS": getattr(settings, "knowledge_user_access", ""),
        "EMBEDDING_BASE_URL": getattr(settings, "embedding_base_url", ""),
        "EMBEDDING_API_TOKEN": getattr(settings, "embedding_api_token", ""),
        "EMBEDDING_MODEL": getattr(settings, "embedding_model", ""),
        "EMBEDDING_REVISION": getattr(settings, "embedding_revision", ""),
        # Market collectors read os.environ directly (Yandex Search / OpenAlex / LLM)
        "YANDEX_API_KEY": getattr(settings, "yandex_api_key", None),
        "YANDEX_FOLDER_ID": getattr(settings, "yandex_folder_id", ""),
        "OPENALEX_API_KEY": getattr(settings, "openalex_api_key", None),
    }
    out = {}
    for k, v in mapping.items():
        if v is None or v == "":
            continue
        # SecretStr → real string
        if hasattr(v, "get_secret_value"):
            v = v.get_secret_value()
        if v and not os.environ.get(k):
            os.environ[k] = str(v)
            out[k] = "set" if "KEY" in k else str(v)
    return out


def knowledge_dsn() -> str | None:
    apply_knowledge_env()
    return os.environ.get("KNOWLEDGE_DATABASE_URL") or None


def embedding_base_url() -> str:
    apply_knowledge_env()
    return os.environ.get("EMBEDDING_BASE_URL", "http://127.0.0.1:8091")
