"""Test doubles for the ports: a settable clock, a recording notifier, a fixed presence."""

from collections.abc import Callable
from datetime import datetime, timedelta

from timetracker.ports import Notification


class FakeClock:
    """Clock whose time only moves when told to."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        """Return the current fake time."""
        return self._now

    def advance(self, minutes: float) -> None:
        """Move time forward."""
        self._now += timedelta(minutes=minutes)


class RecordingNotifier:
    """Notifier that remembers what it was asked to send."""

    def __init__(self) -> None:
        self.sent: list[Notification] = []
        self.callbacks: list[Callable[[str], None] | None] = []

    def send(
        self, notification: Notification, on_action: Callable[[str], None] | None = None
    ) -> None:
        """Record the notification and its action callback."""
        self.sent.append(notification)
        self.callbacks.append(on_action)


class FakePresence:
    """Presence with a settable idle time."""

    def __init__(self, idle: timedelta = timedelta(0)) -> None:
        self.idle = idle

    def input_idle(self) -> timedelta:
        """Return the configured idle time."""
        return self.idle
