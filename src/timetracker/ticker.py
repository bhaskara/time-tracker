"""Periodic alert check: turns due core alerts into user notifications."""

from dataclasses import replace
from datetime import datetime, timedelta

from timetracker.core.alerts import Alert, AlertKind, idle_nudge_due, session_alerts
from timetracker.core.accounting import break_cap
from timetracker.core.model import Rules, Session
from timetracker.ports import Clock, Notification, Notifier, Presence
from timetracker.tracker import Tracker

SIGN_OFF_ACTION = "signoff"

NUDGE = Notification(
    title="No session running",
    body="Start a session or sign off for the day.",
    actions=((SIGN_OFF_ACTION, "Sign off"),),
)


def _minutes(d: timedelta) -> int:
    """Round a duration to whole minutes."""
    return round(d.total_seconds() / 60)


def alert_notification(alert: Alert, sessions: tuple[Session, ...], rules: Rules) -> Notification:
    """Word a timed alert for the user.

    Parameters
    ----------
    alert : Alert
        The alert to describe.
    sessions : tuple[Session, ...]
        History containing the alert's session (used for the break cap).
    rules : Rules
        Accounting constants.

    Returns
    -------
    Notification
        Title and body naming the session and how long it has run.
    """
    s = alert.session
    name = s.label or "work session"
    if alert.kind is AlertKind.PLANNED_END:
        return Notification(
            title=f"Time's up: {name}",
            body=f"The planned {_minutes(s.planned)} min are done. End, take a break, or carry on.",
        )
    if alert.kind is AlertKind.OVERRUN:
        over = alert.at - (s.start + s.planned)
        return Notification(
            title=f"Still going: {name}", body=f"{_minutes(over)} min past the planned end."
        )
    cap = break_cap(sessions, s, rules)
    return Notification(title="Break over", body=f"The {_minutes(cap)} min of break credit are used up.")


class AlertTicker:
    """Checks for due alerts each time ``tick`` is called.

    Holds the only mutable alert state: when it last ticked and when it last
    sent an idle nudge. Neither is persisted, so alerts that became due while
    the server was down are not replayed.

    Parameters
    ----------
    tracker : Tracker
        Application service.
    notifier : Notifier
        Where notifications go.
    presence : Presence
        Reports whether the user is at the computer.
    clock : Clock
        Time source.
    alert_popups : bool
        Whether session alerts (planned end, overrun reminders, break over)
        show a pop-up as well as chiming. The idle nudge always shows one,
        since it carries the sign-off action.
    """

    def __init__(
        self,
        tracker: Tracker,
        notifier: Notifier,
        presence: Presence,
        clock: Clock,
        alert_popups: bool = False,
    ) -> None:
        self._alert_popups = alert_popups
        self._tracker = tracker
        self._notifier = notifier
        self._presence = presence
        self._clock = clock
        self._last_tick: datetime = clock.now()
        self._last_nudge: datetime | None = None

    def _on_action(self, name: str) -> None:
        """Handle the user picking an action on a notification."""
        if name == SIGN_OFF_ACTION:
            self._tracker.sign_off()

    def _nudge_due(self, sessions: tuple[Session, ...], now: datetime) -> bool:
        """Decide on the idle nudge, asking for presence only when it matters."""
        rules = self._tracker.rules
        signed_off = self._tracker.day_config(self._tracker.today()).signed_off

        def due(input_idle: timedelta) -> bool:
            return idle_nudge_due(
                sessions,
                now,
                rules,
                signed_off=signed_off,
                input_idle=input_idle,
                last_nudge=self._last_nudge,
            )

        return due(timedelta(0)) and due(self._presence.input_idle())

    def tick(self) -> tuple[Notification, ...]:
        """Send whatever notifications have become due since the last tick.

        Returns
        -------
        tuple[Notification, ...]
            The notifications sent. If several timed alerts fell due since
            the last tick (for example across a laptop suspend) only the
            latest is sent.
        """
        now = self._clock.now()
        sessions = self._tracker.settle()
        rules = self._tracker.rules
        sent: list[Notification] = []

        alerts = session_alerts(sessions, self._last_tick, now, rules)
        self._last_tick = now
        if alerts:
            notification = alert_notification(alerts[-1], sessions, rules)
            sent.append(replace(notification, popup=self._alert_popups))

        if self._nudge_due(sessions, now):
            self._last_nudge = now
            sent.append(NUDGE)

        for notification in sent:
            self._notifier.send(notification, self._on_action)
        return tuple(sent)
