import datetime

from threadmill.retry import ExponentialBackoff

SPAM_SCAN_RETRY = ExponentialBackoff(
    base_delay=datetime.timedelta(seconds=1),
    max_delay=datetime.timedelta(hours=1),
    factor=2.0,
    # The delay caps at one hour from attempt 12 on, so this budget spans about a day.
    # Attempt 47 and above overflow the exponential before the cap applies.
    max_retries=40,
)
