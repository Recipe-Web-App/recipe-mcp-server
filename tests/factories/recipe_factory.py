"""Test factories for recipe-related models."""

from __future__ import annotations

from polyfactory.factories.pydantic_factory import ModelFactory

from recipe_mcp_server.models.recipe import Ingredient, Recipe, RecipeCreate


class IngredientFactory(ModelFactory):
    __model__ = Ingredient


class RecipeFactory(ModelFactory):
    __model__ = Recipe


class RecipeCreateFactory(ModelFactory):
    __model__ = RecipeCreate
