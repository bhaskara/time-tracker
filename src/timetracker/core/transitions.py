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


def _describe(s: Session) -> str:
    """Name a session for an error message."""
    return f"the {s.type.value} session '{s.label}'" if s.label else f"a {s.type.value} session"


def place_session(
    sessions: Sequence[Session], target: Session, split_id: str | None = None
) -> tuple[Session, ...]:
    """Put a session into the history, making its neighbours give way.

    Parameters
    ----------
    sessions : Sequence[Session]
        Valid history that does not contain a session with ``target.id``.
    target : Session
        The session to place. It keeps its exact start and end.
    split_id : str, optional
        Id for the second half of a session that ``target`` lands in the
        middle of.

    Returns
    -------
    tuple[Session, ...]
        Valid history containing ``target``. A session that ``target`` partly
        overlaps is trimmed to end at its start or begin at its end. A session
        that ``target`` falls strictly inside is split into the part before
        (keeping its id) and the part after (with ``split_id``).

    Raises
    ------
    ValueError
        If ``target`` would completely cover another session, if a split is
        needed but no ``split_id`` was given, or if the result breaks an
        invariant (for example an active ``target`` that is not last).
    """
    result: list[Session] = []
    for other in validate(sessions):
        overlaps = (other.end is None or other.end > target.start) and (
            target.end is None or other.start < target.end
        )
        if not overlaps:
            result.append(other)
            continue
        starts_before = other.start < target.start
        ends_after = target.end is not None and (other.end is None or other.end > target.end)
        if starts_before and ends_after:
            if split_id is None:
                raise ValueError(f"would split {_describe(other)} in two")
            result.append(replace(other, end=target.start))
            result.append(replace(other, id=split_id, start=target.end))
        elif starts_before:
            result.append(replace(other, end=target.start))
        elif ends_after:
            result.append(replace(other, start=target.end))
        else:
            raise ValueError(f"would completely cover {_describe(other)}; delete that one first")
    result.append(target)
    result.sort(key=lambda s: (s.start, s.end is None, s.end or s.start))
    return validate(result)


def start_session(
    sessions: Sequence[Session], new: Session, rules: Rules
) -> tuple[Session, ...]:
    """Start a new session, cutting short whatever was running at its start.

    Parameters
    ----------
    sessions : Sequence[Session]
        Valid history.
    new : Session
        The session to start. Must have no end. Its start may lie in the
        past (a backdated start).
    rules : Rules
        Accounting constants.

    Returns
    -------
    tuple[Session, ...]
        History with ``new`` appended and the session that was running at
        ``new.start`` ended there (a break past its cap by then ends at the
        cap instead). A break started with no credit is appended too and
        expires immediately.

    Raises
    ------
    ValueError
        If ``new`` already has an end, or if a whole session lies after
        ``new.start`` and would be covered.
    """
    if new.end is not None:
        raise ValueError("a session being started must not have an end")
    return place_session(close_expired_breaks(sessions, new.start, rules), new)


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
