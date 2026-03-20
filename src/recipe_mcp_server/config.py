"""Application configuration via environment variables with RECIPE_MCP_ prefix."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Recipe MCP Server settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="RECIPE_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Server
    server_name: str = "recipe-mcp-server"
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    db_path: Path = Path("./data/recipes.db")

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    cache_default_ttl: int = 3600

    # API Keys
    themealdb_api_key: str = "1"
    usda_api_key: str = ""
    spoonacular_api_key: str = ""

    # OAuth 2.1
    oauth_issuer: str = ""
    oauth_audience: str = ""
    oauth_jwks_url: str = ""

    # Observability
    otlp_endpoint: str = "http://localhost:4317"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
