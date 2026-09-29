"""
Draw the digest mail's week chart as inline SVG.

Nothing here reads the database. The counts come from the digest being mailed,
so a chart always draws the week its mail was about, not the week the reader
opens it.
"""

COLUMN = "#8b5cf6"
WIDTH = 600
HEIGHT = 44
CORNER_RADIUS = 4
MAX_DAYS = 31


def week(counts: list[int]) -> str:
    """Return the window's days as a column chart, tallest day at full height."""
    counts = counts[-MAX_DAYS:]  # the newest days, the ones the mail is about
    days = len(counts)
    gap = 8
    column = (WIDTH - gap * (days - 1)) // days
    tallest = max(counts) or 1
    bars = "".join(
        f'<rect x="{index * (column + gap)}"'
        f' y="{HEIGHT - round(HEIGHT * count / tallest)}"'
        f' width="{column}" height="{round(HEIGHT * count / tallest)}"'
        f' rx="{CORNER_RADIUS}" fill="{COLUMN}"/>'
        for index, count in enumerate(counts)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}"'
        f' width="{WIDTH}" height="{HEIGHT}">'
        f"{bars}</svg>"
    )
