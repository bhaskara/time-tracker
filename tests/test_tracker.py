"""Tests for the Tracker application service."""

from datetime import timedelta

import pytest

from timetracker.core.model import SessionType

WORK, BREAK, DIS = SessionType.WORK, SessionType.BREAK, SessionType.DISTRACTION


def m(minutes: float) -> timedelta:
    """Shorthand for minutes."""
    return timedelta(minutes=minutes)


def test_start_work_and_status(tracker, clock):
    """A started work session shows up as active with time remaining."""
    tracker.start(WORK, "write tests", m(30))
    clock.advance(10)
    view = tracker.status()
    assert view.status.active.label == "write tests"
    assert view.status.remaining == m(20)
    assert view.today.summary.work == m(10)


def test_defaults_follow_last_work_session(tracker, clock):
    """Label and duration default to what was last entered."""
    assert tracker.defaults().planned == m(25)
    tracker.start(WORK, "alpha", m(40))
    clock.advance(5)
    tracker.start(DIS)
    clock.advance(5)
    second = tracker.start(WORK)
    assert (second.label, second.planned) == ("alpha", m(40))


def test_work_break_scenario(tracker, clock):
    """50 min work then a break left running: 60 min counted, break ends itself at 10 min."""
    tracker.start(WORK, "deep work", m(50))
    clock.advance(50)
    tracker.start(BREAK)
    clock.advance(25)
    view = tracker.status()
    assert view.status.active is None
    assert view.today.summary.counted == m(60)
    brk = view.today.sessions[-1].session
    assert brk.end - brk.start == m(10)


def test_distraction_scenario(tracker, clock):
    """10 min work then 3 min distraction: 10 min work, 13 min distraction."""
    tracker.start(WORK, "task", m(25))
    clock.advance(10)
    tracker.start(DIS)
    clock.advance(3)
    tracker.end()
    summary = tracker.day().summary
    assert (summary.work, summary.distraction) == (m(10), m(13))


def test_end_without_active_raises(tracker):
    """Ending with nothing running is an error."""
    with pytest.raises(ValueError, match="no active session"):
        tracker.end()


def test_end_after_break_expired_returns_the_break(tracker, clock):
    """Ending a break that already hit its cap reports it as ending at the cap."""
    tracker.start(WORK, "task", m(50))
    clock.advance(50)
    tracker.start(BREAK)
    clock.advance(30)
    ended = tracker.end()
    assert ended.type is BREAK and ended.end - ended.start == m(10)


def test_planned_on_non_work_rejected(tracker):
    """A planned duration on a break is refused and nothing is stored."""
    with pytest.raises(ValueError):
        tracker.start(BREAK, planned=m(5))
    assert tracker.day().sessions == ()


def test_target_default_and_override(tracker):
    """The target defaults to 8 h and can be set per day."""
    today = tracker.today()
    assert tracker.day_config(today).target == timedelta(hours=8)
    tracker.set_target(today, timedelta(hours=6))
    assert tracker.day().summary.target == timedelta(hours=6)


def test_sign_off_ends_active_session_and_start_clears_it(tracker, clock):
    """Signing off ends the running session; starting again clears the sign-off."""
    tracker.start(WORK, "task", m(25))
    clock.advance(10)
    assert tracker.sign_off().signed_off
    assert tracker.status().status.active is None
    assert tracker.day().summary.work == m(10)
    tracker.start(WORK)
    assert not tracker.day_config(tracker.today()).signed_off


def test_day_view_accounts_each_session(tracker, clock):
    """Each listed session carries its own counted and distraction amounts."""
    tracker.start(WORK, "task", m(50))
    clock.advance(50)
    tracker.start(BREAK)
    clock.advance(10)
    tracker.start(DIS)
    clock.advance(4)
    tracker.end()
    amounts = [(v.amounts.counted, v.amounts.distraction) for v in tracker.day().sessions]
    assert amounts == [(m(50), m(0)), (m(10), m(0)), (m(0), m(14))]


def test_break_without_credit_refused(tracker, clock):
    """A break with no work directly before it is refused and nothing is recorded."""
    with pytest.raises(ValueError, match="no break credit"):
        tracker.start(BREAK)
    tracker.start(WORK, "task", m(50))
    clock.advance(50)
    tracker.start(BREAK)
    clock.advance(10)
    with pytest.raises(ValueError, match="no break credit"):
        tracker.start(BREAK)
    assert len(tracker.day().sessions) == 2
