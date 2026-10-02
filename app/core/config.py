from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "modAIJet:latest"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_cache_dir: str | None = None
    embedding_allow_download: bool = False
    allow_registration: bool = True
    jwt_secret: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    chunk_size: int = 700
    chunk_overlap: int = 100
    rag_top_k: int = 5
    max_concurrent_llm_requests: int = 4
    max_upload_bytes: int = 10 * 1024 * 1024
    data_dir: str = "./data/modai"
    auto_create_schema: bool = False
    indexing_job_timeout_seconds: int = 900
    indexing_max_retries: int = 3
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
