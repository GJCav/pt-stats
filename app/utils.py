import humanize
import functools
from datetime import datetime, timezone

naturalsize = functools.partial(humanize.naturalsize, binary=True)


def shorten(text: str, max_length: int) -> str:
    """Shorten a string to a maximum length, adding ellipsis if necessary."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
