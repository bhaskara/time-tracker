"""Ports: the interfaces through which the application touches the outside world."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

from timetracker.core.model import DayConfig, DayNotes, Session


class Clock(Protocol):
    """Source of the current time."""

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware datetime."""
        ...


class Store(Protocol):
    """Persistence for sessions and per-day settings."""

    def load_sessions(self, lo: datetime, hi: datetime | None = None) -> tuple[Session, ...]:
        """Return sessions overlapping ``[lo, hi)`` ordered by start.

        An active session counts as extending forever; ``hi=None`` means no
        upper bound.
        """
        ...

    def write_sessions(self, upserts: Sequence[Session], delete_ids: Sequence[str] = ()) -> None:
        """Atomically insert or replace ``upserts`` (by id) and delete ``delete_ids``."""
        ...

    def get_session(self, session_id: str) -> Session | None:
        """Return the session with this id, or None if there is none."""
        ...

    def last_work_session(self) -> Session | None:
        """Return the work session with the latest start, if any."""
        ...

    def get_day(self, day: date) -> DayConfig | None:
        """Return the stored settings for ``day``, or None if never set."""
        ...

    def put_day(self, config: DayConfig) -> None:
        """Insert or replace the settings for ``config.day``."""
        ...

    def get_notes(self, day: date) -> DayNotes | None:
        """Return the saved notes for ``day``, or None if never saved."""
        ...

    def latest_notes_before(self, day: date) -> DayNotes | None:
        """Return the saved notes of the latest day strictly before ``day``, if any."""
        ...

    def put_notes(self, notes: DayNotes) -> None:
        """Insert or replace the notes for ``notes.day``."""
        ...


@dataclass(frozen=True)
class Notification:
    """A message for the user.

    Attributes
    ----------
    title : str
        Short headline.
    body : str
        One line of detail.
    sound : bool
        Whether to play the chime.
    popup : bool
        Whether to show a pop-up. With ``False`` only the chime is played.
    actions : tuple[tuple[str, str], ...]
        ``(name, button text)`` pairs offered on the notification.
    """

    title: str
    body: str
    sound: bool = True
    popup: bool = True
    actions: tuple[tuple[str, str], ...] = ()


class Notifier(Protocol):
    """Delivers notifications to the user."""

    def send(
        self, notification: Notification, on_action: Callable[[str], None] | None = None
    ) -> None:
        """Deliver ``notification`` without blocking.

        If the user picks one of its actions, ``on_action`` is called later
        with that action's name.
        """
        ...


class Presence(Protocol):
    """Reports whether the user is at the computer."""

    def input_idle(self) -> timedelta:
        """Return an estimate of the time since the user's last input."""
        ...
