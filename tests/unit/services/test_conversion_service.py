"""Tests for ConversionService."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from recipe_mcp_server.services.conversion_service import ConversionService


class TestConvert:
    """Volume, weight, and temperature conversions."""

    def test_volume_cups_to_ml(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "cup", "ml")
        assert result == pytest.approx(236.588)

    def test_volume_tbsp_to_tsp(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "tbsp", "tsp")
        assert result == pytest.approx(14.787 / 4.929)

    def test_weight_lb_to_g(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "lb", "g")
        assert result == pytest.approx(453.592)

    def test_weight_kg_to_oz(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "kg", "oz")
        assert result == pytest.approx(1000.0 / 28.3495)

    def test_same_unit_returns_same_amount(
        self,
        conversion_service: ConversionService,
    ) -> None:
        assert conversion_service.convert(42.0, "cup", "cup") == 42.0

    def test_unit_aliases_cups(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "cups", "ml")
        assert result == pytest.approx(236.588)

    def test_unit_aliases_tablespoons(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "tablespoons", "teaspoons")
        assert result == pytest.approx(14.787 / 4.929)

    def test_unit_aliases_pounds(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "pounds", "grams")
        assert result == pytest.approx(453.592)

    def test_unknown_unit_raises(self, conversion_service: ConversionService) -> None:
        with pytest.raises(ValueError, match="Unknown unit"):
            conversion_service.convert(1.0, "foo", "bar")


class TestTemperature:
    """Temperature conversions."""

    def test_f_to_c(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert_temperature(212.0, "f", "c")
        assert result == pytest.approx(100.0)

    def test_c_to_f(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert_temperature(100.0, "c", "f")
        assert result == pytest.approx(212.0)

    def test_c_to_k(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert_temperature(0.0, "c", "k")
        assert result == pytest.approx(273.15)

    def test_k_to_f(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert_temperature(373.15, "k", "f")
        assert result == pytest.approx(212.0)

    def test_same_temp_unit(self, conversion_service: ConversionService) -> None:
        assert conversion_service.convert_temperature(100.0, "c", "c") == 100.0

    def test_temperature_via_convert(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(32.0, "fahrenheit", "celsius")
        assert result == pytest.approx(0.0)


class TestDensityConversion:
    """Volume <-> weight using ingredient densities."""

    def test_cup_flour_to_grams(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(1.0, "cup", "g", ingredient="flour")
        assert result == pytest.approx(236.588 * 0.593)

    def test_grams_butter_to_cups(self, conversion_service: ConversionService) -> None:
        result = conversion_service.convert(100.0, "g", "cup", ingredient="butter")
        expected_ml = 100.0 / 0.911
        expected_cups = expected_ml / 236.588
        assert result == pytest.approx(expected_cups)

    def test_cross_category_no_ingredient_raises(
        self,
        conversion_service: ConversionService,
    ) -> None:
        with pytest.raises(ValueError, match="without specifying an ingredient"):
            conversion_service.convert(1.0, "cup", "g")

    def test_cross_category_unknown_ingredient_raises(
        self,
        conversion_service: ConversionService,
    ) -> None:
        with pytest.raises(ValueError, match="No density data"):
            conversion_service.convert(1.0, "cup", "g", ingredient="unicorn dust")


class TestAPIFallback:
    """Fallback to Spoonacular API."""

    async def test_api_fallback_on_unknown_density(
        self,
        mock_spoonacular_client: AsyncMock,
    ) -> None:
        mock_spoonacular_client.convert_amounts.return_value = {"targetAmount": 140.0}
        service = ConversionService(spoonacular_client=mock_spoonacular_client)

        result = await service.convert_with_api_fallback(
            1.0,
            "cup",
            "g",
            ingredient="unusual spice",
        )
        assert result == pytest.approx(140.0)
        mock_spoonacular_client.convert_amounts.assert_called_once()

    async def test_api_fallback_uses_local_first(
        self,
        mock_spoonacular_client: AsyncMock,
    ) -> None:
        service = ConversionService(spoonacular_client=mock_spoonacular_client)

        result = await service.convert_with_api_fallback(
            1.0,
            "cup",
            "ml",
            ingredient="water",
        )
        assert result == pytest.approx(236.588)
        mock_spoonacular_client.convert_amounts.assert_not_called()

    async def test_api_fallback_no_client_raises(self) -> None:
        service = ConversionService(spoonacular_client=None)
        with pytest.raises(ValueError):
            await service.convert_with_api_fallback(
                1.0,
                "cup",
                "g",
                ingredient="unknown",
            )

    async def test_api_fallback_api_returns_none(
        self,
        mock_spoonacular_client: AsyncMock,
    ) -> None:
        mock_spoonacular_client.convert_amounts.return_value = {}
        service = ConversionService(spoonacular_client=mock_spoonacular_client)

        with pytest.raises(ValueError, match="Spoonacular could not convert"):
            await service.convert_with_api_fallback(
                1.0,
                "cup",
                "g",
                ingredient="mystery",
            )
