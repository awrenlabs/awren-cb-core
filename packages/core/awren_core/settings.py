"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration via environment variables."""

    database_url: str = "postgresql+psycopg://awren:awren@localhost:5432/awren"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "awren2026"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379/0"
    api_base_url: str = "http://localhost:8000"
    # --- LLM Provider Configuration ---
    llm_provider: str = "openai"
    """LLM provider to use. Options: openai, anthropic, openrouter, custom_openai."""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""
    """Custom base URL for OpenAI-compatible APIs (used when provider=custom_openai)."""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    # --- Embedding Configuration ---
    openai_embedding_model: str = "text-embedding-3-small"
    """OpenAI embedding model for vector generation. Dimensions auto-resolve."""
    openai_embedding_dimensions: int = 1536
    """Vector dimensions for the embedding model.
    text-embedding-3-small = 1536, text-embedding-3-large = 3072, ada-002 = 1536.
    """
    log_level: str = "INFO"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
