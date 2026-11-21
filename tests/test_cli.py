"""Tests for the tt command, run in-process against the real FastAPI app."""

import pytest
from fastapi.testclient import TestClient

from timetracker.api.app import create_app
from timetracker.cli.main import ApiError, build_parser, clock, duration, error_detail, run, start_body
from timetracker.adapters.sqlite_store import SqliteStore
from timetracker.core.model import Rules
from timetracker.tracker import Tracker
from timetracker.workspaces import Workspace, Workspaces

from .conftest import SequentialIds


class InProcessClient:
    """CLI client that calls the FastAPI app directly instead of over a socket."""

    def __init__(self, http: TestClient) -> None:
        self._http = http

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        """Perform the request, mapping error statuses to ApiError like the real client."""
        response = self._http.request(method, path, json=body)
        if response.status_code >= 400:
            raise ApiError(error_detail(response.content))
        return response.json()


class UnreachableClient:
    """Client for a server that is not running."""

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        """Always fail."""
        raise ApiError("cannot reach the server")


@pytest.fixture
def cli(tracker) -> InProcessClient:
    """Client wired to an app over the test tracker."""
    return InProcessClient(TestClient(create_app(Workspaces.single(tracker))))


def test_formatters():
    """Clock and duration formats."""
    assert (clock(754), clock(3725), clock(-5)) == ("12:34", "1:02:05", "0:00")
    assert (duration(45), duration(420), duration(7500), duration(0)) == ("45s", "7m", "2h 05m", "0m")


def test_start_body_parsing():
    """A leading number is minutes, the rest is the label, omissions are left out."""
    assert start_body([]) == {"type": "work"}
    assert start_body(["30"]) == {"type": "work", "planned_minutes": 30.0}
    assert start_body(["write", "report"]) == {"type": "work", "label": "write report"}
    assert start_body(["30", "write", "report"]) == {
        "type": "work",
        "planned_minutes": 30.0,
        "label": "write report",
    }


def test_status_idle(cli):
    """A fresh tracker reports idle with zero totals."""
    assert run(["status"], cli) == (0, "idle\ntoday: 0m counted of 8h 00m (0%) · distraction 0m")
    assert run(["status", "--short"], cli) == (0, "idle")


def test_no_command_means_status(cli):
    """Bare `tt` behaves like `tt status`."""
    assert run([], cli) == run(["status"], cli)


def test_start_then_status_counts_down(cli, clock):
    """Starting prints the new state; status shows time left, then overrun."""
    assert run(["start", "30", "write", "report"], cli) == (0, "work 30:00 left · write report")
    clock.advance(10)
    assert run(["status", "--short"], cli) == (0, "work 20:00 left · write report")
    clock.advance(23.5)
    assert run(["status", "--short"], cli) == (0, "work +3:30 over · write report")


def test_start_without_arguments_reuses_last_values(cli, clock):
    """`tt start` alone repeats the last label and duration."""
    run(["start", "40", "alpha"], cli)
    clock.advance(5)
    run(["end"], cli)
    assert run(["start"], cli) == (0, "work 40:00 left · alpha")


def test_break_distract_end_and_today(cli, clock):
    """A full sequence, ending with the day listing and totals."""
    run(["start", "50", "deep work"], cli)
    clock.advance(50)
    assert run(["break"], cli) == (0, "break 10:00 left")
    clock.advance(10)
    assert run(["distract"], cli) == (0, "distraction 0:00")
    clock.advance(3)
    code, text = run(["end"], cli)
    assert (code, text.splitlines()[0]) == (0, "ended distraction")
    code, text = run(["today"], cli)
    lines = text.splitlines()
    assert code == 0 and len(lines) == 4
    assert lines[0].split()[1:] == ["work", "50m", "deep", "work"]
    assert lines[-1] == "today: 1h 00m counted of 8h 00m (12%) · distraction 13m"


def test_idle_and_signed_off_status(cli, clock):
    """After ending, status shows idle time; after sign-off it says so."""
    run(["start", "25", "x"], cli)
    clock.advance(25)
    run(["end"], cli)
    clock.advance(12)
    assert run(["status", "--short"], cli) == (0, "idle 12m")
    assert run(["signoff"], cli)[1].splitlines()[0] == "signed off"
    assert run(["status", "--short"], cli) == (0, "signed off")


def test_target(cli):
    """Setting the target changes the totals line."""
    assert run(["target", "6"], cli) == (0, "today: 0m counted of 6h 00m (0%) · distraction 0m")


def test_refusals_and_unreachable_server_exit_nonzero(cli):
    """Server refusals and connection failures give exit code 1 with the reason."""
    assert run(["end"], cli) == (1, "error: no active session to end")
    assert run(["break"], cli) == (1, "error: no break credit: a break has to follow work")
    assert run(["status"], UnreachableClient()) == (1, "error: cannot reach the server")


def test_started_moves_current_session_back(cli, clock):
    """`tt started 10` after starting late gives ten minutes elapsed."""
    clock.advance(10)
    run(["start", "30", "late"], cli)
    assert run(["started", "10"], cli) == (0, "work 20:00 left · late")
    run(["end"], cli)
    assert run(["started", "5"], cli) == (1, "error: no active session")


def test_ago_backdates_and_cuts_running_session(cli, clock):
    """`tt distract --ago 15` cuts the work session fifteen minutes back."""
    run(["start", "60", "task"], cli)
    clock.advance(40)
    assert run(["distract", "--ago", "15"], cli) == (0, "distraction 15:00")
    lines = run(["today"], cli)[1].splitlines()
    assert lines[0].split()[1:3] == ["work", "25m"]
    run(["end"], cli)
    assert run(["start", "--ago", "2", "20", "next"], cli) == (0, "work 18:00 left · next")


def test_note_appends_to_working_memory(cli, tracker):
    """`tt note` adds a bullet to today's working memory."""
    assert run(["note", "look", "into", "X"], cli) == (0, "noted")
    assert tracker.notes().body == "- look into X\n"


def test_help_prints_guide_without_the_server():
    """`tt help` works with no server and mentions every command the parser knows."""
    code, text = run(["help"], UnreachableClient())
    assert code == 0 and "SESSION TYPES" in text
    commands = build_parser()._subparsers._group_actions[0].choices
    missing = [name for name in commands if f"tt {name}" not in text]
    assert missing == []


@pytest.fixture
def two(tracker, clock) -> InProcessClient:
    """Client for a server with a default workspace and a ``personal`` one."""
    personal = Tracker(SqliteStore(":memory:"), clock, Rules(), id_factory=SequentialIds())
    workspaces = Workspaces([Workspace("work", tracker), Workspace("personal", personal)])
    return InProcessClient(TestClient(create_app(workspaces)))


def test_workspace_option_selects_the_workspace(two, clock, monkeypatch):
    """`tt -w personal` and $TT_WORKSPACE act on that workspace; plain tt stays on work."""
    monkeypatch.delenv("TT_WORKSPACE", raising=False)
    assert run(["start", "30", "report"], two) == (0, "work 30:00 left · report")
    clock.advance(10)
    assert run(["-w", "personal", "start", "40", "cook"], two) == (0, "work 40:00 left · cook")
    assert run(["status", "--short"], two) == (0, "idle 0m")
    assert run(["workspaces"], two) == (
        0,
        "* work         idle 0m\n  personal     work 40:00 left · cook",
    )
    monkeypatch.setenv("TT_WORKSPACE", "personal")
    assert run(["status", "--short"], two) == (0, "work 40:00 left · cook")
    assert run(["-w", "work", "status", "--short"], two) == (0, "idle 0m")


def test_unknown_workspace_is_named_in_the_error(two, monkeypatch):
    """A workspace the server does not have gives an error listing the ones it has."""
    monkeypatch.delenv("TT_WORKSPACE", raising=False)
    assert run(["-w", "nope", "status"], two) == (
        1,
        "error: unknown workspace 'nope' (known: work, personal)",
    )
