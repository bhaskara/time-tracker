"""Tests for timed session alerts and the idle nudge."""

from datetime import datetime

from timetracker.core.alerts import AlertKind, idle_nudge_due, session_alerts

from .conftest import TZ, at, brk, m, work


def kinds_and_minutes(alerts):
    """Reduce alerts to (kind, minutes after base time) pairs."""
    return [(a.kind, (a.at - at(0)) / m(1)) for a in alerts]


def test_no_alert_before_planned_end(rules):
    """Nothing is due while the session is within its planned time."""
    assert session_alerts((work(0, None, planned=25),), at(0), at(24), rules) == ()


def test_planned_end_then_five_minute_reminders(rules):
    """Chime at the planned end, then every five minutes while it continues."""
    alerts = session_alerts((work(0, None, planned=25),), at(0), at(36), rules)
    assert kinds_and_minutes(alerts) == [
        (AlertKind.PLANNED_END, 25),
        (AlertKind.OVERRUN, 30),
        (AlertKind.OVERRUN, 35),
    ]


def test_window_is_exclusive_at_start_inclusive_at_end(rules):
    """Consecutive windows deliver each alert exactly once."""
    sessions = (work(0, None, planned=25),)
    first = session_alerts(sessions, at(20), at(25), rules)
    second = session_alerts(sessions, at(25), at(30), rules)
    assert kinds_and_minutes(first) == [(AlertKind.PLANNED_END, 25)]
    assert kinds_and_minutes(second) == [(AlertKind.OVERRUN, 30)]


def test_no_reminders_after_session_ends(rules):
    """An ended session stops producing reminders."""
    alerts = session_alerts((work(0, 27, planned=25),), at(0), at(60), rules)
    assert kinds_and_minutes(alerts) == [(AlertKind.PLANNED_END, 25)]


def test_break_ended_alert_at_cap(rules):
    """A break left running alerts when it reaches its cap."""
    alerts = session_alerts((work(0, 50), brk(50, None)), at(50), at(61), rules)
    assert kinds_and_minutes(alerts) == [(AlertKind.BREAK_ENDED, 60)]


def test_no_break_alert_if_ended_early(rules):
    """A break ended before its cap does not alert."""
    assert session_alerts((work(0, 50), brk(50, 55)), at(50), at(61), rules) == ()


def nudge(sessions, now, rules, signed_off=False, input_idle=m(0), last_nudge=None):
    """Call idle_nudge_due with defaults for a present, not-signed-off user."""
    return idle_nudge_due(
        sessions, now, rules, signed_off=signed_off, input_idle=input_idle, last_nudge=last_nudge
    )


def test_nudge_after_ten_idle_minutes(rules):
    """The nudge waits ten minutes after the last session ended."""
    sessions = (work(0, 25),)
    assert not nudge(sessions, at(34), rules)
    assert nudge(sessions, at(35), rules)


def test_no_nudge_while_session_active_or_no_history(rules):
    """An active session, or a day with no sessions, never nudges."""
    assert not nudge((work(0, None),), at(60), rules)
    assert not nudge((), at(60), rules)


def test_no_nudge_when_signed_off(rules):
    """Signing off silences the nudge."""
    assert not nudge((work(0, 25),), at(60), rules, signed_off=True)


def test_no_nudge_when_away_then_nudge_on_return(rules):
    """No nudge without recent input; it fires once input resumes."""
    sessions = (work(0, 25),)
    assert not nudge(sessions, at(60), rules, input_idle=m(20))
    assert nudge(sessions, at(90), rules, input_idle=m(0.5))


def test_nudge_repeats_every_ten_minutes(rules):
    """After a nudge, the next one waits another ten minutes."""
    sessions = (work(0, 25),)
    assert not nudge(sessions, at(40), rules, last_nudge=at(35))
    assert nudge(sessions, at(45), rules, last_nudge=at(35))


def test_nudge_from_earlier_idle_period_does_not_delay(rules):
    """A nudge sent before the latest session does not count."""
    sessions = (work(0, 25), work(40, 65))
    assert nudge(sessions, at(75), rules, last_nudge=at(70 - 33))


def test_no_nudge_on_a_new_day(rules):
    """Yesterday's sessions do not trigger nudges today."""
    sessions = (work(0, 25),)
    assert not nudge(sessions, datetime(2026, 11, 12, 9, 0, tzinfo=TZ), rules)
