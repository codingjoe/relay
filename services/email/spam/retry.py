import datetime

from threadmill.retry import ExponentialBackoff

SPAM_SCAN_RETRY = ExponentialBackoff(
    base_delay=datetime.timedelta(seconds=1),
    max_delay=datetime.timedelta(hours=1),
    factor=2.0,
    # A failed scan must never lose a message, so retry effectively forever:
    # 1_000_000 hourly attempts span about 114 years.
    max_retries=1_000_000,
)
