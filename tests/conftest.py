"""Fixtures wiring a tracker to an in-memory store and a fake clock."""

from datetime import datetime
from itertools import count
from zoneinfo import ZoneInfo

import pytest

from timetracker.adapters.sqlite_store import SqliteStore
from timetracker.core.model import Rules
from timetracker.tracker import Tracker

from .fakes import FakeClock

T0 = datetime(2026, 11, 11, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


class SequentialIds:
    """Id factory producing s1, s2, ... for readable assertions."""

    def __init__(self) -> None:
        self._counter = count(1)

    def __call__(self) -> str:
        """Return the next id."""
        return f"s{next(self._counter)}"


@pytest.fixture
def clock() -> FakeClock:
    """Clock starting at 9:00 AM Pacific."""
    return FakeClock(T0)


@pytest.fixture
def store() -> SqliteStore:
    """Empty in-memory store."""
    return SqliteStore(":memory:")


@pytest.fixture
def tracker(store: SqliteStore, clock: FakeClock) -> Tracker:
    """Tracker over the in-memory store and fake clock."""
    return Tracker(store, clock, Rules(), id_factory=SequentialIds())
