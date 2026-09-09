def build_timeline(timings):
    """
    Yield profile chart events for a message's timings.

    Every event spans its own measured start and finish, so the chart shows
    real leg durations and the gaps between bars show queueing and retry
    delays the way a browser network waterfall does.
    """
    for timing in sorted(
        timings, key=lambda timing: (timing.started_at, timing.created_at)
    ):
        yield timing.event
