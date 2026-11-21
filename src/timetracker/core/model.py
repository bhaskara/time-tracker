"""Domain model: session records and the tunable accounting rules."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from zoneinfo import ZoneInfo


class SessionType(Enum):
    """Kind of tracked session."""

    WORK = "work"
    BREAK = "break"
    DISTRACTION = "distraction"


@dataclass(frozen=True)
class Session:
    """One tracked interval. These raw facts are the only thing stored.

    Attributes
    ----------
    id : str
        Unique identifier, supplied by the caller.
    type : SessionType
        Kind of session.
    start : datetime
        Timezone-aware start time.
    end : datetime or None
        Timezone-aware end time, or None while the session is active.
    label : str
        What the session is for. May be empty for breaks and distractions.
    planned : timedelta or None
        Intended duration. Required for work sessions, None otherwise.
    """

    id: str
    type: SessionType
    start: datetime
    end: datetime | None = None
    label: str = ""
    planned: timedelta | None = None

    def __post_init__(self) -> None:
        """Reject records that can never be valid on their own."""
        if self.start.tzinfo is None:
            raise ValueError(f"session {self.id}: start must be timezone-aware")
        if self.end is not None:
            if self.end.tzinfo is None:
                raise ValueError(f"session {self.id}: end must be timezone-aware")
            if self.end < self.start:
                raise ValueError(f"session {self.id}: end {self.end} precedes start {self.start}")
        if self.type is SessionType.WORK:
            if self.planned is None or self.planned <= timedelta(0):
                raise ValueError(f"session {self.id}: work needs a positive planned duration")
        elif self.planned is not None:
            raise ValueError(f"session {self.id}: only work sessions have a planned duration")

    @property
    def is_active(self) -> bool:
        """True while the session has no recorded end."""
        return self.end is None

    def end_or(self, now: datetime) -> datetime:
        """Return the recorded end, or ``now`` for an active session."""
        return now if self.end is None else self.end


@dataclass(frozen=True)
class Rules:
    """Tunable constants of the accounting rules.

    Attributes
    ----------
    break_fraction : float
        Break credit earned per unit of preceding contiguous work.
    break_max : timedelta
        Upper limit on a single break's credit.
    contiguity_gap : timedelta
        Largest untracked gap that still chains two sessions together.
    distraction_cost : timedelta
        Context-switch cost added to every distraction session.
    day_start_hour : int
        Local hour at which a tracking day begins.
    timezone : ZoneInfo
        Zone in which the day boundary is evaluated.
    default_target : timedelta
        Daily target used when none is set for a day.
    overrun_repeat : timedelta
        Interval between reminders once a work session passes its planned end.
    idle_nudge_after : timedelta
        Time without an active session before nudging, and the repeat interval.
    presence_window : timedelta
        The user counts as present if their last input was within this window.
    """

    break_fraction: float = 0.2
    break_max: timedelta = timedelta(minutes=15)
    contiguity_gap: timedelta = timedelta(minutes=5)
    distraction_cost: timedelta = timedelta(minutes=10)
    day_start_hour: int = 2
    timezone: ZoneInfo = ZoneInfo("America/Los_Angeles")
    default_target: timedelta = timedelta(hours=8)
    overrun_repeat: timedelta = timedelta(minutes=5)
    idle_nudge_after: timedelta = timedelta(minutes=10)
    presence_window: timedelta = timedelta(minutes=3)


@dataclass(frozen=True)
class DayConfig:
    """Per-day settings.

    Attributes
    ----------
    day : date
        The tracking day.
    target : timedelta
        Target for counted time on that day.
    signed_off_at : datetime or None
        When the day was signed off, or None if it has not been.
    """

    day: date
    target: timedelta
    signed_off_at: datetime | None = None

    def __post_init__(self) -> None:
        """Reject non-positive targets."""
        if self.target <= timedelta(0):
            raise ValueError("daily target must be positive")

    @property
    def signed_off(self) -> bool:
        """True once the day has been signed off."""
        return self.signed_off_at is not None


@dataclass(frozen=True)
class DayNotes:
    """A day's working memory: free-form notes kept alongside the sessions.

    Attributes
    ----------
    day : date
        The tracking day.
    body : str
        The notes, in the markup named by ``format``.
    seed_next : str or None
        Starting text for the next day's notes, set at sign-off. None means
        it was never set, in which case the whole body carries over.
    updated_at : datetime or None
        When the notes were last saved; None if never saved.
    format : str
        Markup of ``body`` and ``seed_next``. Only ``"markdown"`` for now.
    """

    day: date
    body: str = ""
    seed_next: str | None = None
    updated_at: datetime | None = None
    format: str = "markdown"
