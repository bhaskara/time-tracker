"""Tests for the HTTP API, driven through FastAPI's test client."""

import pytest
from fastapi.testclient import TestClient

from timetracker.api.app import create_app


@pytest.fixture
def client(tracker) -> TestClient:
    """Client for an app with no ticker."""
    return TestClient(create_app(tracker))


def test_status_when_idle(client):
    """A fresh tracker is idle with default start values and an 8 h target."""
    body = client.get("/api/status").json()
    assert body["active"] is None
    assert body["defaults"] == {"label": "", "planned_minutes": 25}
    assert body["today"]["target_s"] == 8 * 3600


def test_full_day_flow(client, clock):
    """Work, break, distraction and end, with totals matching the rules."""
    r = client.post("/api/sessions", json={"type": "work", "label": "api", "planned_minutes": 50})
    assert r.status_code == 200 and r.json()["planned_s"] == 3000
    clock.advance(20)
    status = client.get("/api/status").json()
    assert (status["active"]["label"], status["remaining_s"], status["overrun"]) == ("api", 1800, False)

    clock.advance(30)
    client.post("/api/sessions", json={"type": "break"})
    clock.advance(10)
    client.post("/api/sessions", json={"type": "distraction"})
    clock.advance(3)
    assert client.post("/api/sessions/end").json()["type"] == "distraction"

    day = client.get("/api/days/today").json()
    assert (day["work_s"], day["break_s"], day["counted_s"]) == (3000, 600, 3600)
    assert day["distraction_s"] == 13 * 60
    assert [s["type"] for s in day["sessions"]] == ["work", "break", "distraction"]
    assert day["progress"] == pytest.approx(1 / 8)


def test_end_with_nothing_active_is_409(client):
    """The tracker's refusal surfaces as a conflict with its message."""
    r = client.post("/api/sessions/end")
    assert r.status_code == 409 and "no active session" in r.json()["detail"]


def test_invalid_requests_rejected(client):
    """Bad types, non-positive durations and malformed dates are rejected."""
    assert client.post("/api/sessions", json={"type": "nap"}).status_code == 422
    assert (
        client.post("/api/sessions", json={"type": "work", "planned_minutes": 0}).status_code == 422
    )
    assert client.post("/api/sessions", json={"type": "break", "planned_minutes": 5}).status_code == 409
    assert client.get("/api/days/yesterdayish").status_code == 422


def test_set_target_and_sign_off(client):
    """Target and sign-off are stored per day and reflected in the day view."""
    assert client.put("/api/days/today", json={"target_hours": 6}).json()["target_s"] == 6 * 3600
    assert client.post("/api/days/today/signoff").json()["signed_off_at"] is not None
    day = client.get("/api/days/2026-11-11").json()
    assert day["target_s"] == 6 * 3600 and day["signed_off_at"] is not None


def test_past_day_is_empty(client):
    """A day with no sessions has zero totals."""
    day = client.get("/api/days/2026-01-01").json()
    assert day["counted_s"] == 0 and day["sessions"] == []
