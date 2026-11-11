"""Derived accounting: break caps, day boundaries, daily totals, current status.

All functions take the full session history as a sequence ordered by start
time with no overlaps (see ``transitions.validate``) and never mutate it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from timetracker.core.model import Rules, Session, SessionType

ZERO = timedelta(0)


def contiguous_work_before(sessions: Sequence[Session], at: datetime, rules: Rules) -> timedelta:
    """Total duration of the unbroken chain of work sessions leading up to ``at``.

    The chain walks backwards from ``at`` and stops at the first break,
    distraction, or untracked gap longer than ``rules.contiguity_gap``.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history.
    at : datetime
        Point in time the chain must lead up to.
    rules : Rules
        Accounting constants.

    Returns
    -------
    timedelta
        Summed duration of the chained work sessions; zero if there are none.
        Sessions starting at or after ``at`` are ignored, and an active
        session is treated as ending at ``at``.
    """
    total = ZERO
    cursor = at
    for s in reversed([s for s in sessions if s.start < at]):
        end = min(s.end_or(at), at)
        if s.type is not SessionType.WORK or cursor - end > rules.contiguity_gap:
            break
        total += end - s.start
        cursor = s.start
    return total


def break_cap(sessions: Sequence[Session], brk: Session, rules: Rules) -> timedelta:
    """Maximum credited length of a break session.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history (may or may not contain ``brk``).
    brk : Session
        The break session; only its start time is used.
    rules : Rules
        Accounting constants.

    Returns
    -------
    timedelta
        ``min(break_fraction * contiguous work before the break, break_max)``.
    """
    earned = contiguous_work_before(sessions, brk.start, rules) * rules.break_fraction
    return min(earned, rules.break_max)


def day_of(t: datetime, rules: Rules) -> date:
    """Tracking day that instant ``t`` belongs to (days start at ``day_start_hour`` local)."""
    local = t.astimezone(rules.timezone)
    return (local - timedelta(hours=rules.day_start_hour)).date()


def day_bounds(day: date, rules: Rules) -> tuple[datetime, datetime]:
    """Half-open interval ``[start, end)`` of instants belonging to tracking day ``day``."""
    boundary = time(hour=rules.day_start_hour)
    start = datetime.combine(day, boundary, tzinfo=rules.timezone)
    end = datetime.combine(day + timedelta(days=1), boundary, tzinfo=rules.timezone)
    return start, end


def _overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> timedelta:
    """Length of the intersection of two intervals (zero if disjoint)."""
    return max(min(a_end, b_end) - max(a_start, b_start), ZERO)


@dataclass(frozen=True)
class DaySummary:
    """Totals for one tracking day.

    Attributes
    ----------
    day : date
        The tracking day.
    work : timedelta
        Time in work sessions, including overrun past the planned end.
    break_credit : timedelta
        Break time that counts as work (each break clipped to its cap).
    distraction : timedelta
        Time in distraction sessions plus the fixed cost per session.
    target : timedelta
        The day's target for counted time.
    """

    day: date
    work: timedelta
    break_credit: timedelta
    distraction: timedelta
    target: timedelta

    @property
    def counted(self) -> timedelta:
        """Time counting towards the target: work plus credited breaks."""
        return self.work + self.break_credit

    @property
    def progress(self) -> float:
        """Counted time as a fraction of the target (may exceed 1)."""
        return self.counted / self.target


def day_summary(
    sessions: Sequence[Session],
    day: date,
    now: datetime,
    rules: Rules,
    target: timedelta | None = None,
) -> DaySummary:
    """Compute the totals for one tracking day.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history; may span many days.
    day : date
        Tracking day to summarise.
    now : datetime
        Current instant; an active session is counted up to here.
    rules : Rules
        Accounting constants.
    target : timedelta, optional
        The day's target; defaults to ``rules.default_target``. Must be positive.

    Returns
    -------
    DaySummary
        A session crossing the day boundary contributes only the part inside
        the day. A distraction's fixed cost is charged to the day it started.
    """
    lo, hi = day_bounds(day, rules)
    work = break_credit = distraction = ZERO
    for s in sessions:
        end = s.end_or(now)
        if s.type is SessionType.WORK:
            work += _overlap(s.start, end, lo, hi)
        elif s.type is SessionType.BREAK:
            credited_end = min(end, s.start + break_cap(sessions, s, rules))
            break_credit += _overlap(s.start, credited_end, lo, hi)
        else:
            distraction += _overlap(s.start, end, lo, hi)
            if lo <= s.start < hi:
                distraction += rules.distraction_cost
    return DaySummary(
        day=day,
        work=work,
        break_credit=break_credit,
        distraction=distraction,
        target=rules.default_target if target is None else target,
    )


@dataclass(frozen=True)
class SessionAmounts:
    """How one whole session is accounted, ignoring day boundaries.

    Attributes
    ----------
    duration : timedelta
        Raw length of the session (up to now if active).
    counted : timedelta
        Part that counts towards the daily target.
    distraction : timedelta
        Distraction time charged, including the fixed cost.
    """

    duration: timedelta
    counted: timedelta
    distraction: timedelta


def session_amounts(
    sessions: Sequence[Session], s: Session, now: datetime, rules: Rules
) -> SessionAmounts:
    """Account for a single session.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history containing the sessions before ``s``.
    s : Session
        The session to account for.
    now : datetime
        Current instant; used as the end of an active session.
    rules : Rules
        Accounting constants.

    Returns
    -------
    SessionAmounts
        Work counts in full, a break up to its cap, a distraction not at all
        but is charged its duration plus ``rules.distraction_cost``.
    """
    duration = s.end_or(now) - s.start
    if s.type is SessionType.WORK:
        return SessionAmounts(duration, duration, ZERO)
    if s.type is SessionType.BREAK:
        return SessionAmounts(duration, min(duration, break_cap(sessions, s, rules)), ZERO)
    return SessionAmounts(duration, ZERO, duration + rules.distraction_cost)


@dataclass(frozen=True)
class Status:
    """What is happening at one instant.

    Attributes
    ----------
    active : Session or None
        The session in progress, if any. A break past its cap is not active.
    elapsed : timedelta or None
        Time since the active session started.
    remaining : timedelta or None
        Time left until the planned end (work) or the cap (break). Negative
        for a work session in overrun. None for distractions or when idle.
    """

    active: Session | None
    elapsed: timedelta | None = None
    remaining: timedelta | None = None

    @property
    def overrun(self) -> bool:
        """True if a work session has passed its planned end."""
        return self.remaining is not None and self.remaining < ZERO


def current_status(sessions: Sequence[Session], now: datetime, rules: Rules) -> Status:
    """Describe the session in progress at ``now``.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history.
    now : datetime
        Current instant.
    rules : Rules
        Accounting constants.

    Returns
    -------
    Status
        Idle status if there is no session without an end, or if the open
        session is a break that has already reached its cap.
    """
    if not sessions or not sessions[-1].is_active:
        return Status(active=None)
    s = sessions[-1]
    elapsed = now - s.start
    if s.type is SessionType.WORK:
        return Status(s, elapsed, s.planned - elapsed)
    if s.type is SessionType.BREAK:
        remaining = break_cap(sessions, s, rules) - elapsed
        return Status(s, elapsed, remaining) if remaining > ZERO else Status(active=None)
    return Status(s, elapsed, None)
