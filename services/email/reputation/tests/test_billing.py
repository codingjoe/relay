from decimal import Decimal

import pytest

from services.email.reputation.billing import money, month_cost, overage_price


@pytest.mark.django_db
class TestMonthCost:
    def test_inside_the_allowance__is_free(self, settings):
        settings.RELAY_FREE_MONTHLY_MESSAGES = 1000
        settings.RELAY_PRICE_PER_1000_MESSAGES = 10.0

        assert month_cost(1000) == Decimal("0.00")
        assert month_cost(0) == Decimal("0.00")

    def test_past_the_allowance__bills_every_thousand(self, settings):
        settings.RELAY_FREE_MONTHLY_MESSAGES = 1000
        settings.RELAY_PRICE_PER_1000_MESSAGES = 10.0

        assert month_cost(1500) == Decimal("5.00")
        assert month_cost(2000) == Decimal("10.00")

    def test_without_a_price__is_free(self, settings):
        settings.RELAY_FREE_MONTHLY_MESSAGES = 1
        settings.RELAY_PRICE_PER_1000_MESSAGES = 0.0

        assert month_cost(5000) == Decimal("0.00")


@pytest.mark.django_db
class TestMoney:
    def test_formats_with_the_currency_symbol(self, settings):
        settings.RELAY_CURRENCY = "EUR "

        assert money(Decimal("1234.5")) == "EUR 1,234.50"

    def test_nothing_is_empty(self, settings):
        assert money(Decimal("0.00")) == ""
        assert money(None) == ""


@pytest.mark.django_db
class TestOveragePrice:
    def test_without_a_price__has_none(self, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = 0.0

        assert overage_price() is None

    def test_with_a_price__formats_it(self, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = 2.5
        settings.RELAY_CURRENCY = "$"

        assert overage_price() == "$2.50"
