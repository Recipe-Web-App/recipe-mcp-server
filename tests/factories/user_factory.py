"""Test factories for user-related models."""

from __future__ import annotations

from polyfactory.factories.pydantic_factory import ModelFactory

from recipe_mcp_server.models.user import Favorite, UserPreferences


class UserPreferencesFactory(ModelFactory):
    __model__ = UserPreferences


class FavoriteFactory(ModelFactory):
    __model__ = Favorite
