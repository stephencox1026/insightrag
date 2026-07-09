"""Centralized configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into the process so OPENAI_API_KEY (no INSIGHTRAG_ prefix) is visible.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INSIGHTRAG_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM / embeddings
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    # openai | ollama | offline
    llm_provider: str = "openai"
    chat_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"
    ollama_base_url: str = "http://127.0.0.1:11434"
    offline: bool = False

    # Database: Postgres when database_url is set, else SQLite file
    database_url: str | None = None

    # Paths (SQLite + file index fallback)
    data_dir: Path = Path("data")
    index_dir: Path = Path("data/index")
    db_path: Path = Path("data/warehouse.db")

    # Retrieval
    top_k: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 120
    hybrid_alpha: float = 0.5

    # UI / API
    api_url: str | None = None

    @property
    def uses_ollama(self) -> bool:
        return self.llm_provider.strip().lower() == "ollama"

    @property
    def is_offline(self) -> bool:
        """True when chat/SQL should not call a generative model."""
        provider = self.llm_provider.strip().lower()
        if self.offline or provider == "offline":
            return True
        if provider == "ollama":
            return False
        key = (self.openai_api_key or "").strip()
        return not key

    @property
    def uses_postgres(self) -> bool:
        return bool(self.database_url)

    @property
    def index_backend(self) -> str:
        return "postgres" if self.uses_postgres else "file"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.uses_postgres:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
