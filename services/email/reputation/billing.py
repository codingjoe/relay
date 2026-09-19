from decimal import Decimal

from django.conf import settings


def month_cost(messages):
    """
    Return what `messages` cost this month, past the free plan allowance.

    The allowance is free, and every 1,000 messages above it cost
    `settings.RELAY_PRICE_PER_1000_MESSAGES`, rounded to cents. A price of
    zero, or a month inside the allowance, costs nothing.
    """
    billable = max(messages - settings.RELAY_FREE_MONTHLY_MESSAGES, 0)
    price = Decimal(str(settings.RELAY_PRICE_PER_1000_MESSAGES))
    return (price * billable / Decimal(1000)).quantize(Decimal("0.01"))


def money(cost):
    """Return `cost` with the billing currency in front of it."""
    if not cost:
        return ""
    return f"{settings.RELAY_CURRENCY}{cost:,.2f}"


def overage_price():
    """Return the price per 1,000 messages, or None when sending is free."""
    if not settings.RELAY_PRICE_PER_1000_MESSAGES:
        return None
    return money(Decimal(str(settings.RELAY_PRICE_PER_1000_MESSAGES)))
