"""Tests for the HTTP API, driven through FastAPI's test client."""

from datetime import timedelta

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


def test_serves_web_page_and_assets(client):
    """The day view and its script and stylesheet are served from the root."""
    page = client.get("/")
    assert page.status_code == 200 and "Time Tracker" in page.text
    assert client.get("/app.js").status_code == 200
    assert client.get("/style.css").status_code == 200
    assert client.get("/common.js").status_code == 200
    review = client.get("/review.html")
    assert review.status_code == 200 and "Totals per week" in review.text
    assert client.get("/review.js").status_code == 200
    signoff = client.get("/signoff.html")
    assert signoff.status_code == 200 and "Start of the next day" in signoff.text
    assert client.get("/signoff.js").status_code == 200
    assert client.get("/markdown.js").status_code == 200


def test_backdate_edit_insert_delete(client, clock):
    """Backdated start, editing the running session, inserting and deleting over HTTP."""
    client.post("/api/sessions", json={"type": "work", "label": "task", "planned_minutes": 60})
    clock.advance(40)
    start = (clock.now() - timedelta(minutes=15)).isoformat()
    distraction = client.post("/api/sessions", json={"type": "distraction", "start": start}).json()
    assert client.get("/api/status").json()["elapsed_s"] == 15 * 60

    earlier = (clock.now() - timedelta(minutes=20)).isoformat()
    r = client.patch(f"/api/sessions/{distraction['id']}", json={"start": earlier, "label": "news"})
    assert r.status_code == 200 and r.json()["label"] == "news"
    day = client.get("/api/days/today").json()
    assert [(s["type"], s["duration_s"]) for s in day["sessions"]] == [
        ("work", 20 * 60),
        ("distraction", 20 * 60),
    ]

    inserted = client.post(
        "/api/sessions",
        json={
            "type": "break",
            "start": (clock.now() - timedelta(minutes=30)).isoformat(),
            "end": (clock.now() - timedelta(minutes=25)).isoformat(),
        },
    ).json()
    types = [s["type"] for s in client.get("/api/days/today").json()["sessions"]]
    assert types == ["work", "break", "work", "distraction"]

    assert client.delete(f"/api/sessions/{inserted['id']}").status_code == 200
    assert client.delete(f"/api/sessions/{inserted['id']}").status_code == 404


def test_edit_errors(client, clock):
    """Unknown ids are 404; refused edits are 409 with the reason; naive times are 422."""
    assert client.patch("/api/sessions/nope", json={"label": "x"}).status_code == 404
    session = client.post("/api/sessions", json={"type": "work", "label": "t"}).json()
    future = (clock.now() + timedelta(minutes=5)).isoformat()
    r = client.patch(f"/api/sessions/{session['id']}", json={"start": future})
    assert r.status_code == 409 and "future" in r.json()["detail"]
    r = client.patch(f"/api/sessions/{session['id']}", json={"start": "2026-11-11T08:00:00"})
    assert r.status_code == 422
    r = client.post("/api/sessions", json={"type": "break", "end": clock.now().isoformat()})
    assert r.status_code == 409


def test_month_endpoint(client, clock):
    """The month endpoint returns per-day, per-week and overall totals."""
    client.post("/api/sessions", json={"type": "work", "label": "t", "planned_minutes": 90})
    clock.advance(90)
    client.post("/api/sessions/end")
    body = client.get("/api/months/2026-11").json()
    assert (body["month"], body["today"], len(body["days"])) == ("2026-11", "2026-11-11", 30)
    assert body["days"][10] == {
        "day": "2026-11-11",
        "work_s": 5400,
        "break_s": 0,
        "counted_s": 5400,
        "distraction_s": 0,
        "target_s": 28800,
    }
    assert len(body["weeks"]) == 6 and body["total"]["counted_s"] == 5400
    assert body["total"]["days_worked"] == 1
    assert client.get("/api/months/current").json()["month"] == "2026-11"
    assert client.get("/api/months/2026-13").status_code == 422
    assert client.get("/api/months/nonsense").status_code == 422


def test_break_after_endpoint(client, clock):
    """POST /api/sessions/{id}/break adds the earned break; refusals are 409, unknown ids 404."""
    session = client.post("/api/sessions", json={"type": "work", "label": "t"}).json()
    assert client.post(f"/api/sessions/{session['id']}/break").status_code == 409
    clock.advance(50)
    client.post("/api/sessions/end")
    clock.advance(30)
    added = client.post(f"/api/sessions/{session['id']}/break").json()
    assert added["type"] == "break"
    assert client.get("/api/days/today").json()["counted_s"] == 3600
    assert client.post("/api/sessions/nope/break").status_code == 404


def test_notes_endpoints(client, clock):
    """Working memory can be read, saved, appended to, and seeds the next day."""
    notes = client.get("/api/days/today/notes").json()
    assert (notes["day"], notes["body"], notes["seed_next"], notes["format"]) == (
        "2026-11-11",
        "",
        None,
        "markdown",
    )
    saved = client.put("/api/days/today/notes", json={"body": "# plan"}).json()
    assert saved["body"] == "# plan" and saved["updated_at"] is not None
    appended = client.post("/api/days/today/notes/append", json={"text": "idea"}).json()
    assert appended["body"] == "# plan\n- idea\n"
    assert client.post("/api/days/today/notes/append", json={"text": " "}).status_code == 409
    client.put("/api/days/today/notes", json={"seed_next": "carry"})
    assert client.get("/api/days/2026-11-12/notes").json()["body"] == "carry"
    clock.advance(24 * 60)
    assert client.get("/api/days/today/notes").json()["body"] == "carry"
