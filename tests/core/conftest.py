"""Shared helpers for core tests: a fixed base time and compact session builders."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from timetracker.core.model import Rules, Session, SessionType

TZ = ZoneInfo("America/Los_Angeles")
# 9:00 AM local on an ordinary weekday, well away from the 2 AM boundary.
T0 = datetime(2026, 11, 11, 9, 0, tzinfo=TZ)


def m(minutes: float) -> timedelta:
    """Shorthand for a timedelta in minutes."""
    return timedelta(minutes=minutes)


def at(minutes: float) -> datetime:
    """Instant ``minutes`` after the base time."""
    return T0 + m(minutes)


def work(start: float, end: float | None, planned: float = 25, sid: str | None = None) -> Session:
    """Work session with times given as minutes after the base time."""
    return Session(
        id=sid or f"w{start}",
        type=SessionType.WORK,
        start=at(start),
        end=None if end is None else at(end),
        label="task",
        planned=m(planned),
    )


def other(kind: SessionType, start: float, end: float | None) -> Session:
    """Break or distraction session with times as minutes after the base time."""
    return Session(
        id=f"{kind.value}{start}",
        type=kind,
        start=at(start),
        end=None if end is None else at(end),
    )


def brk(start: float, end: float | None) -> Session:
    """Break session."""
    return other(SessionType.BREAK, start, end)


def dis(start: float, end: float | None) -> Session:
    """Distraction session."""
    return other(SessionType.DISTRACTION, start, end)


@pytest.fixture
def rules() -> Rules:
    """Default rules."""
    return Rules()
