from decimal import Decimal

from services.email.reputation.billing import money, month_cost, overage_price


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

    def test_with_a_negative_allowance__bills_from_zero(self, settings):
        settings.RELAY_FREE_MONTHLY_MESSAGES = -100
        settings.RELAY_PRICE_PER_1000_MESSAGES = 10.0

        assert month_cost(0) == Decimal("0.00")
        assert month_cost(50) == Decimal("0.50")

    def test_with_a_negative_price__is_free(self, settings):
        settings.RELAY_FREE_MONTHLY_MESSAGES = 0
        settings.RELAY_PRICE_PER_1000_MESSAGES = -5.0

        assert month_cost(5000) == Decimal("0.00")


class TestMoney:
    def test_formats_in_euro(self):
        assert money(Decimal("1234.5")) == "€1,234.50"

    def test_zero__formats_in_euro(self):
        assert money(Decimal("0.00")) == "€0.00"


class TestOveragePrice:
    def test_without_a_price__has_none(self, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = 0.0

        assert overage_price() is None

    def test_with_a_price__formats_it(self, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = 2.5

        assert overage_price() == "€2.50"

    def test_with_a_negative_price__has_none(self, settings):
        settings.RELAY_PRICE_PER_1000_MESSAGES = -5.0

        assert overage_price() is None
