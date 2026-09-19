from decimal import Decimal

from django.conf import settings


def month_cost(messages):
    """Return what `messages` cost this month, past the free tier allowance."""
    billable = max(messages - max(settings.RELAY_FREE_MONTHLY_MESSAGES, 0), 0)
    price = max(Decimal(0), Decimal(str(settings.RELAY_PRICE_PER_1000_MESSAGES)))
    return (price * billable / Decimal(1000)).quantize(Decimal("0.01"))


def money(cost):
    """Return `cost` in euro, the currency relay bills in."""
    return f"€{cost:,.2f}"


def overage_price():
    """Return the price per 1,000 messages, or None when sending is free."""
    price = max(Decimal(0), Decimal(str(settings.RELAY_PRICE_PER_1000_MESSAGES)))
    return money(price) if price else None
