"""Workspaces: independent trackers (e.g. work, personal) with light coordination.

Each workspace has its own store, tracker and alert ticker, so its sessions,
targets, sign-offs and notes are completely separate. The only coupling is
attention: one person can do one thing at a time, so starting a session in
one workspace ends the session running in any other, and a workspace does not
nag about "no session running" while another one has a session running.
"""

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from timetracker.config import DEFAULT_WORKSPACE
from timetracker.core.model import Session, SessionType
from timetracker.ports import Notification
from timetracker.ticker import AlertTicker
from timetracker.tracker import SessionEdit, Tracker


@dataclass(frozen=True)
class Workspace:
    """One independent tracker and, optionally, the ticker raising its alerts.

    Attributes
    ----------
    name : str
        Name used in URLs and on the command line.
    tracker : Tracker
        Application service over the workspace's own store.
    ticker : AlertTicker or None
        Alert ticker for ``tracker``; None if the workspace sends no alerts.
    """

    name: str
    tracker: Tracker
    ticker: AlertTicker | None = None


class Workspaces:
    """The set of workspaces served by one server.

    Parameters
    ----------
    workspaces : Sequence[Workspace]
        At least one workspace, with distinct names. The first is the
        default: the one addressed when no workspace is named.

    Raises
    ------
    ValueError
        If ``workspaces`` is empty or two share a name.
    """

    def __init__(self, workspaces: Sequence[Workspace]) -> None:
        if not workspaces:
            raise ValueError("at least one workspace is needed")
        self._by_name = {w.name: w for w in workspaces}
        if len(self._by_name) != len(workspaces):
            raise ValueError("workspace names must be distinct")
        self.default = workspaces[0].name
        # Serialises operations that touch more than one workspace.
        self._lock = threading.RLock()

    @classmethod
    def single(cls, tracker: Tracker, ticker: AlertTicker | None = None) -> "Workspaces":
        """Wrap one tracker as the only workspace, under the default name."""
        return cls([Workspace(DEFAULT_WORKSPACE, tracker, ticker)])

    @property
    def names(self) -> tuple[str, ...]:
        """Workspace names, the default first."""
        return tuple(self._by_name)

    def get(self, name: str) -> Workspace:
        """Return the workspace called ``name``.

        Raises
        ------
        LookupError
            If there is no such workspace.
        """
        if name not in self._by_name:
            raise LookupError(f"unknown workspace: {name}")
        return self._by_name[name]

    def active(self) -> dict[str, Session | None]:
        """Return each workspace's running session (None where idle), by name."""
        return {name: w.tracker.active() for name, w in self._by_name.items()}

    def _end_others(self, name: str, at: datetime | None) -> None:
        """End the sessions running in every workspace except ``name``.

        Each ends at ``at`` if that lies within the session, otherwise now.
        """
        for other, workspace in self._by_name.items():
            if other == name:
                continue
            running = workspace.tracker.active()
            if running is not None:
                workspace.tracker.end(at if at is not None and at > running.start else None)

    def start(
        self,
        name: str,
        type: SessionType,
        label: str | None = None,
        planned: timedelta | None = None,
        start: datetime | None = None,
    ) -> Session:
        """Start a session in one workspace and end those running in the others.

        Parameters
        ----------
        name : str
            Workspace to start the session in.
        type, label, planned, start
            As for ``Tracker.start``.

        Returns
        -------
        Session
            The newly started session. Sessions that were running in other
            workspaces have been ended at the new session's start (or now, if
            they began after it).

        Raises
        ------
        LookupError
            If there is no workspace called ``name``.
        ValueError
            If ``Tracker.start`` refuses; no workspace is changed then.
        """
        with self._lock:
            session = self.get(name).tracker.start(type, label, planned, start)
            self._end_others(name, start)
            return session

    def edit(self, name: str, session_id: str, changes: SessionEdit) -> Session:
        """Edit a session in one workspace.

        Parameters
        ----------
        name : str
            Workspace holding the session.
        session_id, changes
            As for ``Tracker.edit``.

        Returns
        -------
        Session
            The edited session. If the edit reopened it, sessions running in
            other workspaces have been ended now.

        Raises
        ------
        LookupError
            If the workspace or the session does not exist.
        ValueError
            If ``Tracker.edit`` refuses; no workspace is changed then.
        """
        with self._lock:
            session = self.get(name).tracker.edit(session_id, changes)
            if changes.reopen and session.is_active:
                self._end_others(name, None)
            return session

    def tick(self) -> tuple[Notification, ...]:
        """Tick every workspace's alert ticker once.

        Returns
        -------
        tuple[Notification, ...]
            All notifications sent. A workspace's idle nudge is held back
            while a session is running in another workspace.
        """
        with self._lock:
            running = {name for name, session in self.active().items() if session is not None}
            sent: list[Notification] = []
            for name, workspace in self._by_name.items():
                if workspace.ticker is not None:
                    sent.extend(workspace.ticker.tick(suppress_nudge=bool(running - {name})))
            return tuple(sent)
