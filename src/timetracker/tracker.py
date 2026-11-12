"""Application service: applies core transitions to stored sessions.

This is the one place where the pure core meets the store and the clock.
Every operation loads the recent history, applies a pure function, and
persists the difference.
"""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from uuid import uuid4

from timetracker.core.accounting import (
    DaySummary,
    SessionAmounts,
    ZERO,
    Status,
    break_cap,
    current_status,
    day_bounds,
    day_of,
    day_summary,
    session_amounts,
)
from timetracker.core.model import DayConfig, Rules, Session, SessionType
from timetracker.core.transitions import (
    close_expired_breaks,
    end_session,
    place_session,
    start_session,
)
from timetracker.ports import Clock, Store

# How far back history is loaded for an operation. It only needs to reach
# past the chain of contiguous work that determines a break's cap.
HISTORY_WINDOW = timedelta(days=2)
FALLBACK_PLANNED = timedelta(minutes=25)


@dataclass(frozen=True)
class Defaults:
    """Values offered when starting a work session: those last used."""

    label: str
    planned: timedelta


@dataclass(frozen=True)
class SessionView:
    """A session together with how it is accounted."""

    session: Session
    amounts: SessionAmounts


@dataclass(frozen=True)
class DayView:
    """Everything shown for one tracking day."""

    config: DayConfig
    summary: DaySummary
    sessions: tuple[SessionView, ...]


@dataclass(frozen=True)
class StatusView:
    """Snapshot of the present moment."""

    now: datetime
    status: Status
    defaults: Defaults
    today: DayView
    day_start_hour: int


@dataclass(frozen=True)
class SessionEdit:
    """Changes to apply to a session; ``None`` leaves a field as it is.

    Attributes
    ----------
    type : SessionType or None
        New kind of session.
    label : str or None
        New label.
    start : datetime or None
        New start time.
    end : datetime or None
        New end time.
    planned : timedelta or None
        New planned duration (work only).
    reopen : bool
        If true, remove the end so the session is running again.
    """

    type: SessionType | None = None
    label: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    planned: timedelta | None = None
    reopen: bool = False


def _new_id() -> str:
    """Generate a unique session id."""
    return uuid4().hex


class Tracker:
    """Coordinates the store, the clock and the core rules.

    All methods are safe to call from multiple threads; they are serialised
    by an internal lock.

    Parameters
    ----------
    store : Store
        Persistence adapter.
    clock : Clock
        Time source.
    rules : Rules
        Accounting constants.
    id_factory : Callable[[], str], optional
        Generator of unique session ids.
    """

    def __init__(
        self,
        store: Store,
        clock: Clock,
        rules: Rules,
        id_factory: Callable[[], str] = _new_id,
    ) -> None:
        self._store = store
        self._clock = clock
        self.rules = rules
        self._id_factory = id_factory
        self._lock = threading.RLock()

    def _commit(self, old: Sequence[Session], new: Sequence[Session]) -> None:
        """Persist the difference between two histories."""
        before = set(old)
        kept = {s.id for s in new}
        upserts = [s for s in new if s not in before]
        deletes = [s.id for s in old if s.id not in kept]
        if upserts or deletes:
            self._store.write_sessions(upserts, deletes)

    def settle(self) -> tuple[Session, ...]:
        """Close any break that has reached its cap and return recent history.

        Returns
        -------
        tuple[Session, ...]
            Sessions overlapping the last ``HISTORY_WINDOW``, ordered, with
            no open break past its cap. The closure is persisted.
        """
        with self._lock:
            now = self._clock.now()
            old = self._store.load_sessions(now - HISTORY_WINDOW)
            new = close_expired_breaks(old, now, self.rules)
            self._commit(old, new)
            return new

    def defaults(self) -> Defaults:
        """Return the label and planned duration of the latest work session."""
        with self._lock:
            last = self._store.last_work_session()
        if last is None:
            return Defaults(label="", planned=FALLBACK_PLANNED)
        return Defaults(label=last.label, planned=last.planned)

    def day_config(self, day: date) -> DayConfig:
        """Return the settings for ``day``, falling back to the default target."""
        with self._lock:
            stored = self._store.get_day(day)
        return stored or DayConfig(day=day, target=self.rules.default_target)

    def today(self) -> date:
        """Return the current tracking day."""
        return day_of(self._clock.now(), self.rules)

    def start(
        self,
        type: SessionType,
        label: str | None = None,
        planned: timedelta | None = None,
        start: datetime | None = None,
    ) -> Session:
        """Start a session, cutting short whatever was running at its start.

        Parameters
        ----------
        type : SessionType
            Kind of session.
        label : str, optional
            What the session is for. For work, defaults to the last work label.
        planned : timedelta, optional
            Intended duration; work only. Defaults to the last one used.
        start : datetime, optional
            When the session really began; defaults to now. The session
            running at that time is ended there.

        Returns
        -------
        Session
            The newly started, still running session. Starting a session
            also clears the current day's sign-off.

        Raises
        ------
        ValueError
            If ``planned`` is given for a non-work session or is not positive,
            if a break is requested with no credit (no work directly before
            it), if ``start`` is in the future, or if a whole session lies
            after ``start``. Nothing is changed in those cases.
        """
        with self._lock:
            now = self._clock.now()
            start = now if start is None else start
            self._check_not_future(now, start)
            if type is SessionType.WORK:
                defaults = self.defaults()
                label = defaults.label if label is None else label
                planned = defaults.planned if planned is None else planned
            new = Session(
                id=self._id_factory(), type=type, start=start, label=label or "", planned=planned
            )
            old = self._store.load_sessions(start - HISTORY_WINDOW)
            updated = start_session(old, new, self.rules)
            if type is SessionType.BREAK and break_cap(updated, new, self.rules) <= ZERO:
                raise ValueError("no break credit: a break has to follow work")
            self._commit(old, updated)
            config = self.day_config(day_of(now, self.rules))
            if config.signed_off:
                self._store.put_day(replace(config, signed_off_at=None))
            return new

    def end(self) -> Session:
        """End the active session now.

        Returns
        -------
        Session
            The ended session. A break already past its cap ends at the cap.

        Raises
        ------
        ValueError
            If no session is active.
        """
        with self._lock:
            now = self._clock.now()
            old = self._store.load_sessions(now - HISTORY_WINDOW)
            new = close_expired_breaks(old, now, self.rules)
            if not new or not new[-1].is_active:
                self._commit(old, new)
                # A break that just expired counts as ended by this call.
                if new != old:
                    return new[-1]
                raise ValueError("no active session to end")
            new = end_session(new, now)
            self._commit(old, new)
            return new[-1]

    @staticmethod
    def _check_not_future(now: datetime, *times: datetime | None) -> None:
        """Refuse times that have not happened yet."""
        if any(t is not None and t > now for t in times):
            raise ValueError("that time is in the future")

    def _place(self, target: Session, earliest: datetime) -> None:
        """Place ``target`` into the stored history from ``earliest`` on and persist."""
        self.settle()
        old = self._store.load_sessions(earliest - HISTORY_WINDOW)
        others = tuple(s for s in old if s.id != target.id)
        self._commit(old, place_session(others, target, split_id=self._id_factory()))

    def add(
        self,
        type: SessionType,
        start: datetime,
        end: datetime,
        label: str = "",
        planned: timedelta | None = None,
    ) -> Session:
        """Record a finished session after the fact.

        Parameters
        ----------
        type : SessionType
            Kind of session.
        start, end : datetime
            When it began and ended; neither may be in the future.
        label : str
            What it was for.
        planned : timedelta, optional
            Planned duration; work only, defaults to the actual duration.

        Returns
        -------
        Session
            The stored session. Sessions it partly overlaps are trimmed and
            one it falls inside is split around it.

        Raises
        ------
        ValueError
            If the times are in the future or out of order, or if it would
            completely cover another session. Nothing is changed then.
        """
        with self._lock:
            self._check_not_future(self._clock.now(), start, end)
            if type is SessionType.WORK and planned is None:
                planned = end - start
            new = Session(
                id=self._id_factory(), type=type, start=start, end=end, label=label, planned=planned
            )
            self._place(new, start)
            return new

    def edit(self, session_id: str, changes: SessionEdit) -> Session:
        """Change a stored session, including the one currently running.

        Parameters
        ----------
        session_id : str
            Id of the session to change.
        changes : SessionEdit
            Fields to change; unset fields keep their value. Changing the
            type to work without a planned duration uses the last one used;
            changing it away from work drops the planned duration.

        Returns
        -------
        Session
            The session as stored. Sessions it now partly overlaps are
            trimmed and one it now falls inside is split around it.

        Raises
        ------
        LookupError
            If there is no session with this id.
        ValueError
            If a time is in the future or out of order, if a planned
            duration is given for a non-work session, or if the result would
            completely cover another session. Nothing is changed then.
        """
        with self._lock:
            current = self._store.get_session(session_id)
            if current is None:
                raise LookupError(f"no session with id {session_id}")
            new_type = changes.type or current.type
            if new_type is SessionType.WORK:
                planned = changes.planned or current.planned or self.defaults().planned
            else:
                if changes.planned is not None:
                    raise ValueError("only work sessions have a planned duration")
                planned = None
            edited = Session(
                id=current.id,
                type=new_type,
                start=changes.start or current.start,
                end=None if changes.reopen else (changes.end or current.end),
                label=current.label if changes.label is None else changes.label,
                planned=planned,
            )
            self._check_not_future(self._clock.now(), edited.start, edited.end)
            self._place(edited, min(current.start, edited.start))
            return edited

    def delete(self, session_id: str) -> Session:
        """Remove a stored session.

        Returns
        -------
        Session
            The session that was removed. Its neighbours are left as they were.

        Raises
        ------
        LookupError
            If there is no session with this id.
        """
        with self._lock:
            current = self._store.get_session(session_id)
            if current is None:
                raise LookupError(f"no session with id {session_id}")
            self._store.write_sessions([], [session_id])
            return current

    def day(self, day: date | None = None) -> DayView:
        """Return the sessions and totals for a tracking day.

        Parameters
        ----------
        day : date, optional
            Tracking day; defaults to today.

        Returns
        -------
        DayView
            Settings, totals, and every session overlapping the day.
        """
        with self._lock:
            now = self._clock.now()
            self.settle()
            day = day_of(now, self.rules) if day is None else day
            lo, hi = day_bounds(day, self.rules)
            # Load one extra day back so break caps see their preceding work.
            history = self._store.load_sessions(lo - timedelta(days=1), hi)
            config = self.day_config(day)
        summary = day_summary(history, day, now, self.rules, config.target)
        views = tuple(
            SessionView(s, session_amounts(history, s, now, self.rules))
            for s in history
            if s.start < hi and (s.start >= lo or s.end_or(now) > lo)
        )
        return DayView(config=config, summary=summary, sessions=views)

    def status(self) -> StatusView:
        """Return the active session, the start defaults and today's totals."""
        with self._lock:
            now = self._clock.now()
            sessions = self.settle()
            return StatusView(
                now=now,
                status=current_status(sessions, now, self.rules),
                defaults=self.defaults(),
                today=self.day(),
                day_start_hour=self.rules.day_start_hour,
            )

    def set_target(self, day: date, target: timedelta) -> DayConfig:
        """Set the target for a day.

        Raises
        ------
        ValueError
            If ``target`` is not positive.
        """
        with self._lock:
            config = replace(self.day_config(day), target=target)
            self._store.put_day(config)
            return config

    def sign_off(self, day: date | None = None) -> DayConfig:
        """Mark a day as finished.

        Parameters
        ----------
        day : date, optional
            Tracking day; defaults to today.

        Returns
        -------
        DayConfig
            The updated settings. Signing off today also ends the active
            session. Signing off an already signed-off day changes nothing.
        """
        with self._lock:
            now = self._clock.now()
            today = day_of(now, self.rules)
            day = today if day is None else day
            if day == today:
                sessions = self.settle()
                if sessions and sessions[-1].is_active:
                    self.end()
            config = self.day_config(day)
            if not config.signed_off:
                config = replace(config, signed_off_at=now)
                self._store.put_day(config)
            return config
