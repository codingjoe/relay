from services.email.reputation.evaluation import ReputationSummary


def make_stats(**overrides):
    """Return a clean window, with the given fields overridden."""
    return (
        ReputationSummary(
            total_sent=0,
            hard_bounces=0,
            soft_bounces=0,
            complaints=0,
            hard_bounce_rate=0.0,
            complaint_rate=0.0,
            hard_bounce_over_limit=False,
            complaint_over_limit=False,
        )
        | overrides
    )
