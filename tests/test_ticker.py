"""Tests for the alert ticker."""

from datetime import timedelta

import pytest

from timetracker.core.model import SessionType
from timetracker.ticker import NUDGE, AlertTicker

from .fakes import FakePresence, RecordingNotifier

WORK, BREAK = SessionType.WORK, SessionType.BREAK


@pytest.fixture
def notifier() -> RecordingNotifier:
    """Fresh recording notifier."""
    return RecordingNotifier()


@pytest.fixture
def presence() -> FakePresence:
    """Presence reporting the user as active."""
    return FakePresence()


@pytest.fixture
def ticker(tracker, notifier, presence, clock) -> AlertTicker:
    """Ticker wired to the fakes."""
    return AlertTicker(tracker, notifier, presence, clock)


def titles(notifier: RecordingNotifier) -> list[str]:
    """Titles of everything sent so far."""
    return [n.title for n in notifier.sent]


def test_quiet_while_within_planned_time(tracker, ticker, notifier, clock):
    """No notification before the planned end."""
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(24)
    assert ticker.tick() == ()


def test_planned_end_then_overrun_reminders(tracker, ticker, notifier, clock):
    """Chime at the planned end and again five minutes later, each once."""
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(25)
    ticker.tick()
    ticker.tick()
    clock.advance(5)
    ticker.tick()
    assert titles(notifier) == ["Time's up: task", "Still going: task"]
    assert notifier.sent[1].body == "5 min past the planned end."


def test_only_latest_alert_after_long_pause(tracker, ticker, notifier, clock):
    """A long gap between ticks produces one notification, not a burst."""
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(47)
    ticker.tick()
    assert [n.body for n in notifier.sent] == ["20 min past the planned end."]


def test_break_over_notification_and_break_closed(tracker, ticker, notifier, clock):
    """When a break hits its cap the user is told and the break is closed."""
    tracker.start(WORK, "task", timedelta(minutes=50))
    clock.advance(50)
    tracker.start(BREAK)
    clock.advance(10)
    ticker.tick()
    assert titles(notifier) == ["Break over"]
    assert notifier.sent[0].body == "The 10 min of break credit are used up."
    assert tracker.day().sessions[-1].session.end is not None


def test_idle_nudge_only_when_present(tracker, ticker, notifier, presence, clock):
    """The nudge waits for the user to be at the computer."""
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(20)
    tracker.end()
    clock.advance(15)
    presence.idle = timedelta(hours=1)
    assert ticker.tick() == ()
    presence.idle = timedelta(0)
    assert ticker.tick() == (NUDGE,)
    assert ticker.tick() == ()
    clock.advance(10)
    assert ticker.tick() == (NUDGE,)


def test_sign_off_action_signs_off_and_stops_nudges(tracker, ticker, notifier, clock):
    """Choosing 'Sign off' on the nudge signs the day off and silences later nudges."""
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(20)
    tracker.end()
    clock.advance(15)
    ticker.tick()
    assert notifier.sent[-1].actions == (("signoff", "Sign off"),)
    notifier.callbacks[-1]("signoff")
    assert tracker.day_config(tracker.today()).signed_off
    clock.advance(30)
    assert ticker.tick() == ()


def test_session_alerts_chime_without_popup_by_default(tracker, ticker, notifier, clock):
    """Time's-up alerts only chime; the idle nudge still pops up with its action."""
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(25)
    ticker.tick()
    assert (notifier.sent[-1].sound, notifier.sent[-1].popup) == (True, False)
    tracker.end()
    clock.advance(15)
    ticker.tick()
    assert notifier.sent[-1] == NUDGE and NUDGE.popup


def test_session_alert_popups_can_be_enabled(tracker, notifier, presence, clock):
    """With alert_popups on, time's-up alerts pop up as well."""
    ticker = AlertTicker(tracker, notifier, presence, clock, alert_popups=True)
    tracker.start(WORK, "task", timedelta(minutes=25))
    clock.advance(25)
    ticker.tick()
    assert notifier.sent[-1].popup
