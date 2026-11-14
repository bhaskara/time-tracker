"""Tests for the working-memory rules."""

from datetime import date

from timetracker.core.model import DayNotes
from timetracker.core.notes import append_line, initial_body

TODAY = date(2026, 11, 13)
YESTERDAY = date(2026, 11, 12)


def test_no_previous_notes_starts_empty():
    """The very first day starts empty."""
    assert initial_body(TODAY, TODAY, None) == ""


def test_unsigned_previous_day_carries_everything():
    """Without a seed, the whole previous text carries over."""
    assert initial_body(TODAY, TODAY, DayNotes(YESTERDAY, body="# todo\n- x")) == "# todo\n- x"


def test_seed_replaces_body_even_when_empty():
    """A seed set at sign-off is used instead, including an empty one."""
    assert initial_body(TODAY, TODAY, DayNotes(YESTERDAY, body="old", seed_next="carry")) == "carry"
    assert initial_body(TODAY, TODAY, DayNotes(YESTERDAY, body="old", seed_next="")) == ""


def test_past_day_never_inherits():
    """A past day without notes stays empty."""
    assert initial_body(YESTERDAY, TODAY, DayNotes(date(2026, 11, 10), body="old")) == ""


def test_append_line():
    """Appended text becomes a bullet on its own line."""
    assert append_line("", "idea") == "- idea\n"
    assert append_line("# notes", " idea ") == "# notes\n- idea\n"
    assert append_line("# notes\n", "idea") == "# notes\n- idea\n"
