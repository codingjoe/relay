"""
Draw the digest mail's week chart as table cells.

A mail client drops embedded SVG, and most of them do, so the bars are table
cells: a cell's height and background colour are the two things every client
draws. Nothing here reads the database. The counts come from the digest being
mailed, so a chart always draws the week its mail was about, not the week the
reader opens it.
"""

COLUMN = "#8b5cf6"
HEIGHT = 44
CORNER_RADIUS = 4
GAP = 8
MAX_DAYS = 31

CELL_ATTRIBUTES = 'role="presentation" border="0" cellpadding="0" cellspacing="0"'
# The shell's stylesheet aligns every cell to the top, and an inline style is
# what outranks it, so both cells state the bottom they need.
BAR_STYLE = (
    f"background-color:{COLUMN}; border-radius:{CORNER_RADIUS}px;"
    f" vertical-align:bottom; font-size:0; line-height:0"
)


def column(count: int, tallest: int, days: int, gap: bool) -> str:
    """Return one day's column, a coloured cell as tall as its share."""
    height = round(HEIGHT * count / tallest)
    fill = (
        f'<td height="{height}" bgcolor="{COLUMN}"'
        f' style="height:{height}px; {BAR_STYLE}">&nbsp;</td>'
        if height
        else ""
    )
    spacing = f"padding-right:{GAP}px; " if gap else ""
    return (
        f'<td width="{100 / days:.4g}%" valign="bottom"'
        f' style="{spacing}vertical-align:bottom">'
        f'<table {CELL_ATTRIBUTES} width="100%" style="border-collapse:collapse">'
        f"<tr>{fill}</tr></table></td>"
    )


def week(counts: list[int]) -> str:
    """Return the window's days as a column chart, tallest day at full height."""
    counts = counts[-MAX_DAYS:]  # the newest days, the ones the mail is about
    days = len(counts)
    tallest = max(counts) or 1
    columns = "".join(
        column(count, tallest, days, gap=index < days - 1)
        for index, count in enumerate(counts)
    )
    return (
        f'<table {CELL_ATTRIBUTES} width="100%" style="border-collapse:collapse">'
        f"<tr>{columns}</tr></table>"
    )
