"""State transitions: starting and ending sessions.

Every function returns a new tuple of sessions and leaves its input untouched.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from timetracker.core.accounting import break_cap
from timetracker.core.model import Rules, Session, SessionType


def validate(sessions: Sequence[Session]) -> tuple[Session, ...]:
    """Check the history invariants and return the history as a tuple.

    Parameters
    ----------
    sessions : Sequence[Session]
        Candidate history.

    Returns
    -------
    tuple[Session, ...]
        The same sessions, unchanged.

    Raises
    ------
    ValueError
        If ids repeat, sessions are not ordered by start, two sessions
        overlap, or a session other than the last one has no end.
    """
    ids = [s.id for s in sessions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate session ids")
    for prev, nxt in zip(sessions, sessions[1:]):
        if prev.end is None:
            raise ValueError(f"session {prev.id} is still active but is not the last session")
        if nxt.start < prev.end:
            raise ValueError(f"session {nxt.id} starts before session {prev.id} ends")
    return tuple(sessions)


def close_expired_breaks(
    sessions: Sequence[Session], now: datetime, rules: Rules
) -> tuple[Session, ...]:
    """End an open break that has reached its cap.

    Parameters
    ----------
    sessions : Sequence[Session]
        Valid history.
    now : datetime
        Current instant.
    rules : Rules
        Accounting constants.

    Returns
    -------
    tuple[Session, ...]
        History in which an open break whose cap has passed by ``now`` ends
        exactly at ``start + cap``; otherwise the history unchanged.
    """
    sessions = validate(sessions)
    if not sessions:
        return sessions
    last = sessions[-1]
    if last.type is not SessionType.BREAK or not last.is_active:
        return sessions
    cap_end = last.start + break_cap(sessions, last, rules)
    if now < cap_end:
        return sessions
    return (*sessions[:-1], replace(last, end=cap_end))


def start_session(
    sessions: Sequence[Session], new: Session, rules: Rules
) -> tuple[Session, ...]:
    """Start a new session, ending whatever was active at that moment.

    Parameters
    ----------
    sessions : Sequence[Session]
        Valid history.
    new : Session
        The session to start. Must have no end. Its start is the transition
        time and must not precede the start of the active session or the end
        of the last finished one.
    rules : Rules
        Accounting constants.

    Returns
    -------
    tuple[Session, ...]
        History with any active session ended at ``new.start`` (a break past
        its cap ends at the cap instead) and ``new`` appended. A break started
        with no credit is appended too and expires immediately.

    Raises
    ------
    ValueError
        If ``new`` already has an end, or would overlap existing sessions.
    """
    if new.end is not None:
        raise ValueError("a session being started must not have an end")
    sessions = close_expired_breaks(sessions, new.start, rules)
    if sessions and sessions[-1].is_active:
        sessions = end_session(sessions, new.start)
    return validate((*sessions, new))


def end_session(sessions: Sequence[Session], at: datetime) -> tuple[Session, ...]:
    """End the active session.

    Parameters
    ----------
    sessions : Sequence[Session]
        Valid history whose last session is active.
    at : datetime
        End time; must not precede the active session's start.

    Returns
    -------
    tuple[Session, ...]
        History with the last session ended at ``at``.

    Raises
    ------
    ValueError
        If no session is active or ``at`` precedes its start.
    """
    sessions = validate(sessions)
    if not sessions or not sessions[-1].is_active:
        raise ValueError("no active session to end")
    return (*sessions[:-1], replace(sessions[-1], end=at))
