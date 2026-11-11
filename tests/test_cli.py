"""Tests for the tt command, run in-process against the real FastAPI app."""

import pytest
from fastapi.testclient import TestClient

from timetracker.api.app import create_app
from timetracker.cli.main import ApiError, clock, duration, error_detail, run, start_body


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
    return InProcessClient(TestClient(create_app(tracker)))


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
