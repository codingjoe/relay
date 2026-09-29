"""
The chart the digest mail links, drawn as SVG.

Mail clients run no scripts and strip inline SVG, so the chart ships as its own
document behind an image source. Nothing here reads the database: the counts
travel in the query string, which means a chart always draws the week its mail
was about, not the week the reader opens it.
"""

COLUMN = "#8b5cf6"
TRACK = "#6b6b76"
WIDTH = 600
CORNER_RADIUS = 4
MAX_DAYS = 31


def week(counts: list[int], height: int = 44) -> str:
    """
    Return the window's days as a column chart, tallest day at full height.

    Draws at most MAX_DAYS columns, and drops the rest of a longer row, so a
    column stays wide enough to read.
    """
    counts = counts[:MAX_DAYS]
    days = max(len(counts), 1)
    gap = 8
    column = (WIDTH - gap * (days - 1)) // days
    tallest = max(counts or [0]) or 1
    bars = "".join(
        f'<rect x="{index * (column + gap)}"'
        f' y="{height - round(height * count / tallest)}"'
        f' width="{column}" height="{round(height * count / tallest)}"'
        f' rx="{CORNER_RADIUS}" fill="{COLUMN}"/>'
        for index, count in enumerate(counts)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}"'
        f' width="{WIDTH}" height="{height}" role="img">'
        f'<rect y="{height - 2}" width="{WIDTH}" height="2" fill="{TRACK}" fill-opacity="0.25"/>'
        f"{bars}</svg>"
    )
