from django.db.models import QuerySet
from fastmcp.exceptions import ValidationError
from fastmcp.utilities.pagination import CursorState


class InvalidCursorError(ValidationError):
    """Signal a value the pagination state cannot decode."""

    def __init__(self, cursor: str | None) -> None:
        super().__init__(f"Invalid cursor: {cursor}")


def paginate_queryset[ModelType](
    queryset: QuerySet[ModelType],
    cursor: str | None,
    page_size: int,
) -> tuple[list[ModelType], str | None]:
    """Return one page of rows and the cursor for the next page."""
    try:
        offset = CursorState.decode(cursor).offset if cursor else 0
    except (TypeError, ValueError) as error:
        raise InvalidCursorError(cursor) from error
    # One extra row detects a following page without a COUNT query.
    rows = list(queryset[offset : offset + page_size + 1])
    if len(rows) <= page_size:
        return rows, None
    return rows[:page_size], CursorState(offset=offset + page_size).encode()
