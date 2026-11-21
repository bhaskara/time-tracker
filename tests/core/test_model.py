"""Tests for session record validation."""

from datetime import datetime

import pytest

from timetracker.core.model import Session, SessionType

from .conftest import T0, at, m


def test_naive_start_rejected():
    """Naive datetimes are refused."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Session(id="a", type=SessionType.BREAK, start=datetime(2026, 1, 1))


def test_end_before_start_rejected():
    """A session cannot end before it starts."""
    with pytest.raises(ValueError, match="precedes"):
        Session(id="a", type=SessionType.BREAK, start=T0, end=at(-1))


def test_work_requires_planned():
    """Work sessions need a positive planned duration."""
    with pytest.raises(ValueError, match="planned"):
        Session(id="a", type=SessionType.WORK, start=T0)


def test_non_work_rejects_planned():
    """Breaks and distractions carry no planned duration."""
    with pytest.raises(ValueError, match="only work"):
        Session(id="a", type=SessionType.DISTRACTION, start=T0, planned=m(5))
