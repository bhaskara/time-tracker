"""Tests for independent workspaces: separate data, one running session, quiet nudges."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from timetracker.adapters.sqlite_store import SqliteStore
from timetracker.api.app import create_app
from timetracker.core.model import Rules, SessionType
from timetracker.ticker import NUDGE, AlertTicker
from timetracker.tracker import SessionEdit, Tracker
from timetracker.workspaces import Workspace, Workspaces

from .conftest import SequentialIds
from .fakes import FakePresence, RecordingNotifier

WORK = SessionType.WORK


@pytest.fixture
def notifier() -> RecordingNotifier:
    """Fresh recording notifier shared by both workspaces."""
    return RecordingNotifier()


@pytest.fixture
def personal(clock) -> Tracker:
    """Second tracker over its own in-memory store, with a 2 h default target."""
    rules = Rules(default_target=timedelta(hours=2))
    return Tracker(SqliteStore(":memory:"), clock, rules, id_factory=SequentialIds())


@pytest.fixture
def workspaces(tracker, personal, notifier, clock) -> Workspaces:
    """A default ``work`` workspace that nudges and a ``personal`` one that does not."""
    presence = FakePresence()
    return Workspaces(
        [
            Workspace("work", tracker, AlertTicker(tracker, notifier, presence, clock)),
            Workspace(
                "personal",
                personal,
                AlertTicker(personal, notifier, presence, clock, idle_nudge=False, label="personal"),
            ),
        ]
    )


@pytest.fixture
def client(workspaces) -> TestClient:
    """HTTP client over both workspaces."""
    return TestClient(create_app(workspaces))


def test_needs_distinct_names(tracker):
    """An empty or duplicated set of workspaces is refused; unknown names raise."""
    with pytest.raises(ValueError):
        Workspaces([])
    with pytest.raises(ValueError):
        Workspaces([Workspace("a", tracker), Workspace("a", tracker)])
    with pytest.raises(LookupError):
        Workspaces.single(tracker).get("personal")


def test_starting_in_one_workspace_ends_the_other(workspaces, tracker, personal, clock):
    """Only one session runs across workspaces, and each keeps its own history."""
    workspaces.start("work", WORK, "report", timedelta(minutes=30))
    clock.advance(20)
    workspaces.start("personal", WORK, "cook", timedelta(minutes=40))
    assert workspaces.active()["work"] is None
    assert workspaces.active()["personal"].label == "cook"
    assert tracker.day().summary.work == timedelta(minutes=20)
    clock.advance(40)
    workspaces.start("work", WORK)
    assert personal.day().summary.work == timedelta(minutes=40)
    assert [v.session.label for v in tracker.day().sessions] == ["report", "report"]
    assert [v.session.label for v in personal.day().sessions] == ["cook"]


def test_backdated_start_cuts_the_other_workspace_there(workspaces, tracker, clock):
    """A start 10 minutes ago ends the other workspace's session 10 minutes ago."""
    workspaces.start("work", WORK, "report", timedelta(minutes=60))
    clock.advance(30)
    workspaces.start("personal", WORK, "call", timedelta(minutes=15), clock.now() - timedelta(minutes=10))
    assert tracker.day().summary.work == timedelta(minutes=20)


def test_refused_start_leaves_other_workspace_running(workspaces, clock):
    """A break with no credit is refused and does not end the session elsewhere."""
    workspaces.start("work", WORK, "report", timedelta(minutes=30))
    with pytest.raises(ValueError, match="break credit"):
        workspaces.start("personal", SessionType.BREAK)
    assert workspaces.active()["work"] is not None


def test_reopening_a_session_ends_the_other_workspace(workspaces, tracker, personal, clock):
    """Reopening a finished session counts as starting it."""
    first = workspaces.start("personal", WORK, "cook", timedelta(minutes=40))
    clock.advance(10)
    personal.end()
    workspaces.start("work", WORK, "report", timedelta(minutes=30))
    clock.advance(5)
    workspaces.edit("personal", first.id, SessionEdit(reopen=True))
    assert workspaces.active()["work"] is None
    assert workspaces.active()["personal"].id == first.id


def test_nudge_held_back_while_other_workspace_is_busy(workspaces, tracker, notifier, clock):
    """Work does not nag during a personal session, and personal never nags."""
    workspaces.start("work", WORK, "report", timedelta(minutes=30))
    clock.advance(10)
    workspaces.start("personal", WORK, "lunch", timedelta(minutes=60))
    clock.advance(30)
    assert workspaces.tick() == ()
    workspaces.get("personal").tracker.end()
    clock.advance(11)
    assert workspaces.tick() == (NUDGE,)


def test_alerts_from_other_workspaces_are_labelled(workspaces, notifier, clock):
    """A non-default workspace's alert names the workspace in its title."""
    workspaces.start("personal", WORK, "cook", timedelta(minutes=25))
    clock.advance(25)
    (sent,) = workspaces.tick()
    assert sent.title == "[personal] Time's up: cook"


def test_api_serves_each_workspace_under_its_prefix(client, clock):
    """Un-prefixed URLs are the default workspace; /w/<name>/ reaches each one."""
    client.post("/api/sessions", json={"type": "work", "label": "report", "planned_minutes": 30})
    assert client.get("/w/work/api/status").json()["active"]["label"] == "report"
    assert client.get("/w/personal/api/status").json()["active"] is None
    assert client.get("/w/personal/api/status").json()["today"]["target_s"] == 2 * 3600

    clock.advance(10)
    r = client.post("/w/personal/api/sessions", json={"type": "work", "label": "cook", "planned_minutes": 40})
    assert r.status_code == 200
    assert client.get("/api/status").json()["active"] is None
    listing = client.get("/api/workspaces").json()
    assert [(w["name"], w["default"], w["path"]) for w in listing] == [
        ("work", True, "/"),
        ("personal", False, "/w/personal/"),
    ]
    assert [w["active"] and w["active"]["label"] for w in listing] == [None, "cook"]


def test_api_pages_and_unknown_workspace(client):
    """Every workspace serves the web page; an undeclared one is a 404."""
    assert client.get("/").status_code == 200
    assert client.get("/w/personal/").status_code == 200
    assert client.get("/w/personal/review.html").status_code == 200
    assert client.get("/w/nope/api/status").status_code == 404
    assert client.get("/w/nope/").status_code == 404
