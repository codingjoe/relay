from decimal import Decimal

from django.conf import settings


def month_cost(messages):
    """
    Return what `messages` cost this month, past the free tier allowance.

    The allowance is free, and every 1,000 messages above it cost
    `settings.RELAY_PRICE_PER_1000_MESSAGES`, rounded to cents. An
    allowance or price below zero counts as zero. A price of zero, or a
    month inside the allowance, costs nothing.
    """
    billable = max(messages - max(settings.RELAY_FREE_MONTHLY_MESSAGES, 0), 0)
    price = max(Decimal(0), Decimal(str(settings.RELAY_PRICE_PER_1000_MESSAGES)))
    return (price * billable / Decimal(1000)).quantize(Decimal("0.01"))


def money(cost):
    """Return `cost` with the billing currency in front of it."""
    return f"{settings.RELAY_CURRENCY}{cost:,.2f}"


def overage_price():
    """Return the price per 1,000 messages, or None when sending is free."""
    if not settings.RELAY_PRICE_PER_1000_MESSAGES:
        return None
    return money(Decimal(str(settings.RELAY_PRICE_PER_1000_MESSAGES)))
