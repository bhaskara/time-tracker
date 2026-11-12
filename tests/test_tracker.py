"""Tests for the Tracker application service."""

from datetime import timedelta

import pytest

from timetracker.core.model import SessionType
from timetracker.tracker import SessionEdit

from .conftest import T0

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


def spans(tracker) -> list[tuple[str, int, int | None]]:
    """Today's sessions as (type, start minute, end minute) relative to 9:00."""
    def minute(t):
        return None if t is None else round((t - T0) / m(1))

    return [
        (v.session.type.value, minute(v.session.start), minute(v.session.end))
        for v in tracker.day().sessions
    ]


def test_forgot_to_start_then_move_start_back(tracker, clock):
    """Starting ten minutes late and then setting the start to ten minutes ago."""
    clock.advance(10)
    session = tracker.start(WORK, "task", m(30))
    tracker.edit(session.id, SessionEdit(start=clock.now() - m(10)))
    status = tracker.status().status
    assert (status.elapsed, status.remaining) == (m(10), m(20))


def test_distracted_for_the_last_fifteen_minutes(tracker, clock):
    """A backdated distraction cuts the running work session at that point."""
    tracker.start(WORK, "task", m(60))
    clock.advance(40)
    tracker.start(DIS, start=clock.now() - m(15))
    assert spans(tracker) == [("work", 0, 25), ("distraction", 25, None)]
    summary = tracker.day().summary
    assert (summary.work, summary.distraction) == (m(25), m(25))


def test_moving_active_start_back_trims_previous_session(tracker, clock):
    """Moving the running session's start earlier shortens the session before it."""
    tracker.start(WORK, "first", m(30))
    clock.advance(30)
    second = tracker.start(DIS)
    clock.advance(5)
    tracker.edit(second.id, SessionEdit(start=clock.now() - m(15)))
    assert spans(tracker) == [("work", 0, 20), ("distraction", 20, None)]


def test_add_missed_session_splits_surrounding_work(tracker, clock):
    """Recording a past distraction inside a work session splits the work around it."""
    tracker.start(WORK, "task", m(60))
    clock.advance(60)
    tracker.end()
    tracker.add(DIS, T0 + m(20), T0 + m(30))
    assert spans(tracker) == [("work", 0, 20), ("distraction", 20, 30), ("work", 30, 60)]
    labels = [v.session.label for v in tracker.day().sessions]
    assert labels == ["task", "", "task"]


def test_edit_fields_of_finished_session(tracker, clock):
    """Label, type and end of a finished session can be changed; planned follows the type."""
    first = tracker.start(WORK, "task", m(30))
    clock.advance(30)
    tracker.end()
    clock.advance(10)
    edited = tracker.edit(first.id, SessionEdit(label="renamed", end=clock.now() - m(5)))
    assert (edited.label, edited.end - edited.start) == ("renamed", m(35))
    as_distraction = tracker.edit(first.id, SessionEdit(type=DIS))
    assert as_distraction.planned is None
    back_to_work = tracker.edit(first.id, SessionEdit(type=WORK))
    assert back_to_work.planned == m(25)


def test_reopen_last_session(tracker, clock):
    """A session ended by mistake can be set running again."""
    session = tracker.start(WORK, "task", m(30))
    clock.advance(10)
    tracker.end()
    clock.advance(2)
    tracker.edit(session.id, SessionEdit(reopen=True))
    assert tracker.status().status.elapsed == m(12)


def test_edit_refusals_leave_history_unchanged(tracker, clock):
    """Future times, covering another session and unknown ids are refused without changes."""
    first = tracker.start(WORK, "first", m(20))
    clock.advance(20)
    second = tracker.start(WORK, "second", m(20))
    clock.advance(20)
    tracker.end()
    before = spans(tracker)
    with pytest.raises(ValueError, match="future"):
        tracker.edit(second.id, SessionEdit(end=clock.now() + m(5)))
    with pytest.raises(ValueError, match="completely cover the work session 'first'"):
        tracker.edit(second.id, SessionEdit(start=clock.now() - m(60)))
    with pytest.raises(ValueError, match="precedes"):
        tracker.edit(first.id, SessionEdit(end=clock.now() - m(90)))
    with pytest.raises(LookupError):
        tracker.edit("nope", SessionEdit(label="x"))
    with pytest.raises(ValueError, match="future"):
        tracker.start(WORK, start=clock.now() + m(1))
    assert spans(tracker) == before


def test_delete_session(tracker, clock):
    """Deleting removes only that session."""
    first = tracker.start(WORK, "first", m(20))
    clock.advance(20)
    tracker.start(DIS)
    clock.advance(5)
    tracker.end()
    tracker.delete(first.id)
    assert spans(tracker) == [("distraction", 20, 25)]
    with pytest.raises(LookupError):
        tracker.delete(first.id)
