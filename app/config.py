"""
app/config.py — Environment-driven settings via pydantic-settings.
All configuration is loaded from environment variables (or a .env file).
No credentials are hard-coded here.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/media_pipeline"

    # Redis / RQ
    redis_url: str = "redis://localhost:6379/0"

    # File storage
    upload_dir: str = "/app/uploads"

    # Upload constraints
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Allowed MIME types
    allowed_content_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "image/gif",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton (avoids re-reading env on every call)."""
    return Settings()
