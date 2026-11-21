"""Which chimes and nudges are due.

Timed alerts are computed for a window ``(after, until]`` so a caller only has
to remember when it last asked. The idle nudge depends on whether the user is
at the computer, so it is a separate state-based check.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from timetracker.core.accounting import break_cap, day_of
from timetracker.core.model import Rules, Session, SessionType


class AlertKind(Enum):
    """Reason for an alert."""

    PLANNED_END = "planned_end"
    OVERRUN = "overrun"
    BREAK_ENDED = "break_ended"


@dataclass(frozen=True)
class Alert:
    """A timed alert tied to a session.

    Attributes
    ----------
    kind : AlertKind
        Reason for the alert.
    at : datetime
        Instant at which the alert becomes due.
    session : Session
        The session the alert is about.
    """

    kind: AlertKind
    at: datetime
    session: Session


def _work_alerts(s: Session, after: datetime, until: datetime, rules: Rules) -> list[Alert]:
    """Planned-end alert and overrun reminders of one work session within ``(after, until]``."""
    planned_end = s.start + s.planned
    # Alerts stop once the session has ended.
    last = until if s.end is None else min(until, s.end)
    # First reminder index k with planned_end + k * repeat > after.
    k = max(0, (after - planned_end) // rules.overrun_repeat + 1)
    alerts = []
    while (at := planned_end + k * rules.overrun_repeat) <= last:
        alerts.append(Alert(AlertKind.PLANNED_END if k == 0 else AlertKind.OVERRUN, at, s))
        k += 1
    return alerts


def session_alerts(
    sessions: Sequence[Session], after: datetime, until: datetime, rules: Rules
) -> tuple[Alert, ...]:
    """Timed alerts that become due within ``(after, until]``.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history.
    after : datetime
        Exclusive start of the window (typically the previous check).
    until : datetime
        Inclusive end of the window (typically now).
    rules : Rules
        Accounting constants.

    Returns
    -------
    tuple[Alert, ...]
        Ordered by time. A work session yields ``PLANNED_END`` at its planned
        end and ``OVERRUN`` every ``rules.overrun_repeat`` after that until it
        ends. A break yields ``BREAK_ENDED`` at its cap unless it was ended
        before reaching it.
    """
    alerts: list[Alert] = []
    for s in sessions:
        if s.end is not None and s.end <= after:
            continue
        if s.type is SessionType.WORK:
            alerts.extend(_work_alerts(s, after, until, rules))
        elif s.type is SessionType.BREAK:
            cap_end = s.start + break_cap(sessions, s, rules)
            if after < cap_end <= until and (s.end is None or s.end >= cap_end):
                alerts.append(Alert(AlertKind.BREAK_ENDED, cap_end, s))
    return tuple(sorted(alerts, key=lambda a: a.at))


def idle_nudge_due(
    sessions: Sequence[Session],
    now: datetime,
    rules: Rules,
    *,
    signed_off: bool,
    input_idle: timedelta,
    last_nudge: datetime | None,
) -> bool:
    """Decide whether to nudge the user to start a session or sign off.

    Parameters
    ----------
    sessions : Sequence[Session]
        Ordered, non-overlapping history with expired breaks already closed
        (see ``transitions.close_expired_breaks``).
    now : datetime
        Current instant.
    rules : Rules
        Accounting constants.
    signed_off : bool
        Whether the current tracking day has been signed off.
    input_idle : timedelta
        Time since the user's last keyboard or mouse input.
    last_nudge : datetime or None
        When the previous idle nudge was sent, if ever.

    Returns
    -------
    bool
        True only if all hold: no session is active; the last session ended
        in the current tracking day at least ``rules.idle_nudge_after`` ago;
        the day is not signed off; the user gave input within
        ``rules.presence_window``; and no nudge was sent for this idle period
        within the last ``rules.idle_nudge_after``.
    """
    if signed_off or not sessions or sessions[-1].is_active:
        return False
    last_end = sessions[-1].end
    if day_of(last_end, rules) != day_of(now, rules):
        return False
    if now - last_end < rules.idle_nudge_after:
        return False
    if input_idle > rules.presence_window:
        return False
    if last_nudge is not None and last_nudge >= last_end:
        return now - last_nudge >= rules.idle_nudge_after
    return True
