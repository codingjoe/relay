"""
The charts the digest mail links, drawn as SVG.

Mail clients run no scripts and strip inline SVG, so each chart ships as its
own document behind an image source. Nothing here reads the database: the
numbers travel in the query string, which means a chart always draws the week
its mail was about, not the week the reader opens it.
"""

TRACK = "#ece9f3"
MARKER = "#6b6b76"

TONES = {
    "good": "#157a3f",
    "bad": "#c93a3a",
    "primary": "#6200d1",
    "muted": "#9aa0a6",
    "soft": "#cbb6f2",
}

WIDTH = 600


def bar(
    value: float, tone: str = "good", height: int = 12, marker: bool = False
) -> str:
    """Return one horizontal bar filled to `value` per cent of its track."""
    colour = TONES.get(tone, TONES["good"])
    radius = max(height // 2, 1)
    filled = round(WIDTH * min(max(value, 0.0), 100.0) / 100)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}"'
        f' width="{WIDTH}" height="{height}" role="img">'
        f'<rect width="{WIDTH}" height="{height}" rx="{radius}" fill="{TRACK}"/>'
        + (
            f'<rect width="{filled}" height="{height}" rx="{radius}" fill="{colour}"/>'
            if filled
            else ""
        )
        + (
            f'<rect x="{WIDTH - 3}" width="3" height="{height}" fill="{MARKER}"/>'
            if marker
            else ""
        )
        + "</svg>"
    )


def week(counts: list[int], tone: str = "primary", height: int = 44) -> str:
    """Return the window's days as a column chart, tallest day at full height."""
    colour = TONES.get(tone, TONES["primary"])
    days = max(len(counts), 1)
    gap = 8
    column = max((WIDTH - gap * (days - 1)) // days, 1)
    tallest = max(counts or [0]) or 1
    bars = "".join(
        f'<rect x="{index * (column + gap)}"'
        f' y="{height - round(height * count / tallest)}"'
        f' width="{column}" height="{round(height * count / tallest)}"'
        f' rx="{min(column // 2, 4)}" fill="{colour}"/>'
        for index, count in enumerate(counts)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}"'
        f' width="{WIDTH}" height="{height}" role="img">'
        f'<rect y="{height - 2}" width="{WIDTH}" height="2" fill="{TRACK}"/>'
        f"{bars}</svg>"
    )
