"""Rules for the per-day working memory."""

from datetime import date

from timetracker.core.model import DayNotes


def initial_body(day: date, today: date, previous: DayNotes | None) -> str:
    """Starting text for a day whose notes have never been saved.

    Parameters
    ----------
    day : date
        The day being opened.
    today : date
        The current tracking day.
    previous : DayNotes or None
        The most recent saved notes from before ``day``, if any.

    Returns
    -------
    str
        For today or a later day: the previous notes' ``seed_next`` if one was
        set (even an empty one), otherwise their whole body; empty if there
        are no previous notes. For a past day: empty, since a past day never
        inherits anything after the fact.
    """
    if day < today or previous is None:
        return ""
    return previous.body if previous.seed_next is None else previous.seed_next


def append_line(body: str, text: str) -> str:
    """Add ``text`` as a bullet on its own line at the end of ``body``."""
    separator = "" if not body or body.endswith("\n") else "\n"
    return f"{body}{separator}- {text.strip()}\n"
