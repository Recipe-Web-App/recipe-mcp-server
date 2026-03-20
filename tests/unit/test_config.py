"""Unit tests for configuration module."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from recipe_mcp_server.config import Settings

pytestmark = pytest.mark.unit


class TestSettingsDefaults:
    def test_default_server_name(self) -> None:
        settings = Settings()
        assert settings.server_name == "recipe-mcp-server"

    def test_default_transport(self) -> None:
        settings = Settings()
        assert settings.transport == "stdio"

    def test_default_port(self) -> None:
        settings = Settings()
        assert settings.port == 8000

    def test_default_db_path(self) -> None:
        settings = Settings()
        assert settings.db_path == Path("./data/recipes.db")

    def test_default_cache_ttl(self) -> None:
        settings = Settings()
        assert settings.cache_default_ttl == 3600

    def test_default_log_level(self) -> None:
        settings = Settings()
        assert settings.log_level == "INFO"

    def test_default_log_format(self) -> None:
        settings = Settings()
        assert settings.log_format == "json"

    def test_default_themealdb_key(self) -> None:
        settings = Settings()
        assert settings.themealdb_api_key == "1"


class TestSettingsOverrides:
    def test_override_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_TRANSPORT", "http")
        settings = Settings()
        assert settings.transport == "http"

    def test_override_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_PORT", "9000")
        settings = Settings()
        assert settings.port == 9000

    def test_override_db_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_DB_PATH", "/tmp/test.db")
        settings = Settings()
        assert settings.db_path == Path("/tmp/test.db")

    def test_override_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_LOG_LEVEL", "DEBUG")
        settings = Settings()
        assert settings.log_level == "DEBUG"

    def test_override_redis_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_REDIS_URL", "redis://redis:6379/1")
        settings = Settings()
        assert settings.redis_url == "redis://redis:6379/1"

    def test_override_api_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_USDA_API_KEY", "test-usda-key")
        monkeypatch.setenv("RECIPE_MCP_SPOONACULAR_API_KEY", "test-spoon-key")
        settings = Settings()
        assert settings.usda_api_key == "test-usda-key"
        assert settings.spoonacular_api_key == "test-spoon-key"


class TestSettingsValidation:
    def test_invalid_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_TRANSPORT", "websocket")
        with pytest.raises(ValidationError):
            Settings()

    def test_invalid_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_LOG_LEVEL", "TRACE")
        with pytest.raises(ValidationError):
            Settings()

    def test_invalid_log_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RECIPE_MCP_LOG_FORMAT", "xml")
        with pytest.raises(ValidationError):
            Settings()
