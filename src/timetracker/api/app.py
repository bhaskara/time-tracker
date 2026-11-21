"""FastAPI application: JSON endpoints over each workspace's tracker, plus the alert ticker loop.

The default workspace is served at ``/`` (pages) and ``/api`` (endpoints);
every workspace, the default included, is also served under ``/w/<name>/``.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, BaseModel, Field

from timetracker.core.accounting import DaySummary, RangeTotals
from timetracker.core.model import DayConfig, DayNotes, Session, SessionType
from timetracker.tracker import DayView, MonthView, SessionEdit, SessionView, StatusView, Tracker
from timetracker.workspaces import Workspaces

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent.parent / "web"


class StartRequest(BaseModel):
    """Body of a request to start a session."""

    type: Literal["work", "break", "distraction"]
    label: str | None = None
    planned_minutes: float | None = Field(default=None, gt=0)
    # A past start backdates the session; adding an end records a finished one.
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None


class EditRequest(BaseModel):
    """Body of a request to change a session; omitted fields are left alone."""

    type: Literal["work", "break", "distraction"] | None = None
    label: str | None = None
    planned_minutes: float | None = Field(default=None, gt=0)
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    reopen: bool = False


class NotesRequest(BaseModel):
    """Body of a request to save working memory; omitted fields are left alone."""

    body: str | None = None
    seed_next: str | None = None


class AppendRequest(BaseModel):
    """Body of a request to append a line to working memory."""

    text: str


class TargetRequest(BaseModel):
    """Body of a request to set a day's target."""

    target_hours: float = Field(gt=0, le=24)


def _seconds(d: timedelta | None) -> int | None:
    """Encode a duration as whole seconds."""
    return None if d is None else round(d.total_seconds())


def session_json(s: Session) -> dict:
    """Encode a session."""
    return {
        "id": s.id,
        "type": s.type.value,
        "label": s.label,
        "start": s.start.isoformat(),
        "end": None if s.end is None else s.end.isoformat(),
        "planned_s": _seconds(s.planned),
    }


def session_view_json(v: SessionView) -> dict:
    """Encode a session with its accounting."""
    return {
        **session_json(v.session),
        "duration_s": _seconds(v.amounts.duration),
        "counted_s": _seconds(v.amounts.counted),
        "distraction_s": _seconds(v.amounts.distraction),
    }


def day_config_json(c: DayConfig) -> dict:
    """Encode a day's settings."""
    return {
        "day": c.day.isoformat(),
        "target_s": _seconds(c.target),
        "signed_off_at": None if c.signed_off_at is None else c.signed_off_at.isoformat(),
    }


def day_json(v: DayView) -> dict:
    """Encode a day's settings, totals and sessions."""
    return {
        **day_config_json(v.config),
        "work_s": _seconds(v.summary.work),
        "break_s": _seconds(v.summary.break_credit),
        "counted_s": _seconds(v.summary.counted),
        "distraction_s": _seconds(v.summary.distraction),
        "progress": v.summary.progress,
        "sessions": [session_view_json(s) for s in v.sessions],
    }


def notes_json(n: DayNotes) -> dict:
    """Encode a day's working memory."""
    return {
        "day": n.day.isoformat(),
        "body": n.body,
        "seed_next": n.seed_next,
        "format": n.format,
        "updated_at": None if n.updated_at is None else n.updated_at.isoformat(),
    }


def day_summary_json(s: DaySummary) -> dict:
    """Encode one day's totals."""
    return {
        "day": s.day.isoformat(),
        "work_s": _seconds(s.work),
        "break_s": _seconds(s.break_credit),
        "counted_s": _seconds(s.counted),
        "distraction_s": _seconds(s.distraction),
        "target_s": _seconds(s.target),
    }


def range_json(r: RangeTotals) -> dict:
    """Encode totals over a range of days."""
    return {
        "start": r.start.isoformat(),
        "end": r.end.isoformat(),
        "work_s": _seconds(r.work),
        "break_s": _seconds(r.break_credit),
        "counted_s": _seconds(r.counted),
        "distraction_s": _seconds(r.distraction),
        "days_worked": r.days_worked,
    }


def month_json(v: MonthView) -> dict:
    """Encode a month's daily, weekly and overall totals."""
    return {
        "month": v.days[0].day.isoformat()[:7],
        "today": v.today.isoformat(),
        "days": [day_summary_json(d) for d in v.days],
        "weeks": [range_json(w) for w in v.weeks],
        "total": range_json(v.total),
    }


def status_json(v: StatusView) -> dict:
    """Encode the status snapshot."""
    st = v.status
    return {
        "now": v.now.isoformat(),
        "active": None if st.active is None else session_json(st.active),
        "elapsed_s": _seconds(st.elapsed),
        "remaining_s": _seconds(st.remaining),
        "overrun": st.overrun,
        "defaults": {
            "label": v.defaults.label,
            "planned_minutes": v.defaults.planned.total_seconds() / 60,
        },
        "today": day_json(v.today),
        "day_start_hour": v.day_start_hour,
    }


class RevalidatedStaticFiles(StaticFiles):
    """Static files that browsers must revalidate on every load.

    Without a ``Cache-Control`` header browsers guess how long a script stays
    fresh, and can keep running an old ``app.js`` next to a new page after an
    update. ``no-cache`` still allows caching but forces a cheap freshness
    check each time.
    """

    def file_response(self, *args, **kwargs):
        """Build the file (or not-modified) response and mark it for revalidation."""
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


class RedirectTo:
    """Endpoint that redirects to a fixed path.

    Parameters
    ----------
    path : str
        Where to send the browser.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def __call__(self) -> RedirectResponse:
        """Answer with a temporary redirect to the path."""
        return RedirectResponse(self._path)


class TickerLoop:
    """Ticks the workspaces' alert tickers repeatedly as an asyncio task.

    Parameters
    ----------
    workspaces : Workspaces
        The workspaces whose tickers to call.
    interval : float
        Seconds between ticks.
    """

    def __init__(self, workspaces: Workspaces, interval: float) -> None:
        self._workspaces = workspaces
        self._interval = interval

    async def run(self) -> None:
        """Tick forever. A failing tick is logged and the loop continues."""
        while True:
            try:
                await asyncio.to_thread(self._workspaces.tick)
            except Exception:
                # One bad tick must not silence all later alerts.
                logger.exception("alert tick failed")
            await asyncio.sleep(self._interval)


def workspace_path(workspaces: Workspaces, name: str) -> str:
    """URL path (ending in ``/``) under which a workspace's pages and API live."""
    return "/" if name == workspaces.default else f"/w/{name}/"


def workspaces_json(workspaces: Workspaces) -> list[dict]:
    """Encode the list of workspaces with what is running in each."""
    return [
        {
            "name": name,
            "default": name == workspaces.default,
            "path": workspace_path(workspaces, name),
            "active": None if session is None else session_json(session),
        }
        for name, session in workspaces.active().items()
    ]


def _minutes(value: float | None) -> timedelta | None:
    """Decode an optional number of minutes."""
    return None if value is None else timedelta(minutes=value)


def _parse_day(tracker: Tracker, day: str) -> date:
    """Resolve a path segment (``today`` or ISO date) to a tracking day."""
    if day == "today":
        return tracker.today()
    try:
        return date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"not a date: {day}")


def workspace_router(workspaces: Workspaces, name: str) -> APIRouter:
    """Build the API endpoints of one workspace.

    Parameters
    ----------
    workspaces : Workspaces
        All workspaces; starting or reopening a session goes through it so
        that sessions running elsewhere are ended.
    name : str
        The workspace these endpoints read and change. Must exist.

    Returns
    -------
    APIRouter
        Routes relative to the workspace's API root (``/status``,
        ``/sessions``, ...). Operations refused by the tracker yield HTTP 409.
    """
    tracker: Tracker = workspaces.get(name).tracker
    router = APIRouter()

    @router.get("/status")
    def get_status() -> dict:
        """Active session, time remaining, start defaults and today's totals."""
        return status_json(tracker.status())

    @router.post("/sessions")
    def start_session(request: StartRequest) -> dict:
        """Start a session (optionally backdated), or record a finished one if ``end`` is given."""
        kind = SessionType(request.type)
        planned = _minutes(request.planned_minutes)
        try:
            if request.end is not None:
                if request.start is None:
                    raise ValueError("a finished session needs a start as well as an end")
                session = tracker.add(kind, request.start, request.end, request.label or "", planned)
            else:
                session = workspaces.start(name, kind, request.label, planned, request.start)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @router.patch("/sessions/{session_id}")
    def edit_session(session_id: str, request: EditRequest) -> dict:
        """Change a session, including the running one."""
        changes = SessionEdit(
            type=None if request.type is None else SessionType(request.type),
            label=request.label,
            start=request.start,
            end=request.end,
            planned=_minutes(request.planned_minutes),
            reopen=request.reopen,
        )
        try:
            session = workspaces.edit(name, session_id, changes)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @router.post("/sessions/{session_id}/break")
    def break_after(session_id: str) -> dict:
        """Record the break that followed a finished work session."""
        try:
            session = tracker.break_after(session_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @router.delete("/sessions/{session_id}")
    def delete_session(session_id: str) -> dict:
        """Delete a session."""
        try:
            session = tracker.delete(session_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return session_json(session)

    @router.post("/sessions/end")
    def end_session() -> dict:
        """End the active session."""
        try:
            session = tracker.end()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @router.get("/days/{day}")
    def get_day(day: str) -> dict:
        """Sessions and totals for a day (``today`` or ``YYYY-MM-DD``)."""
        return day_json(tracker.day(_parse_day(tracker, day)))

    @router.get("/months/{month}")
    def get_month(month: str) -> dict:
        """Daily, weekly and overall totals for a month (``current`` or ``YYYY-MM``)."""
        if month == "current":
            today = tracker.today()
            return month_json(tracker.month(today.year, today.month))
        try:
            year, number = (int(part) for part in month.split("-"))
            view = tracker.month(year, number)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"not a month: {month}")
        return month_json(view)

    @router.put("/days/{day}")
    def put_day(day: str, request: TargetRequest) -> dict:
        """Set a day's target."""
        config = tracker.set_target(
            _parse_day(tracker, day), timedelta(hours=request.target_hours)
        )
        return day_config_json(config)

    @router.post("/days/{day}/signoff")
    def sign_off(day: str) -> dict:
        """Sign a day off, ending the active session if it is today."""
        return day_config_json(tracker.sign_off(_parse_day(tracker, day)))

    @router.get("/days/{day}/notes")
    def get_notes(day: str) -> dict:
        """A day's working memory."""
        return notes_json(tracker.notes(_parse_day(tracker, day)))

    @router.put("/days/{day}/notes")
    def put_notes(day: str, request: NotesRequest) -> dict:
        """Save a day's working memory and/or the next day's starting text."""
        notes = tracker.set_notes(_parse_day(tracker, day), request.body, request.seed_next)
        return notes_json(notes)

    @router.post("/days/today/notes/append")
    def append_note(request: AppendRequest) -> dict:
        """Append a bullet to today's working memory."""
        try:
            return notes_json(tracker.append_note(request.text))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    return router


def create_app(workspaces: Workspaces, tick_interval: float = 1.0) -> FastAPI:
    """Build the HTTP application.

    Parameters
    ----------
    workspaces : Workspaces
        The workspaces to serve. Those with a ticker are ticked every
        ``tick_interval`` seconds while the app runs.
    tick_interval : float
        Seconds between ticks.

    Returns
    -------
    FastAPI
        The application. The default workspace's API is under ``/api`` and
        its web page at ``/``; each workspace (the default too) is also at
        ``/w/<name>/api`` and ``/w/<name>/``. ``/api/workspaces`` lists them.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if any(workspaces.get(name).ticker is not None for name in workspaces.names):
            task = asyncio.create_task(TickerLoop(workspaces, tick_interval).run())
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="Time Tracker", lifespan=lifespan)

    @app.get("/api/workspaces")
    def get_workspaces() -> list[dict]:
        """Every workspace, its URL path and its running session."""
        return workspaces_json(workspaces)

    app.include_router(workspace_router(workspaces, workspaces.default), prefix="/api")
    for name in workspaces.names:
        app.include_router(workspace_router(workspaces, name), prefix=f"/w/{name}/api")

    # Mounted last so they only handle paths the API routes did not match;
    # the root mount comes after the more specific workspace ones.
    for name in workspaces.names:
        # Without the trailing slash the pages' relative URLs would resolve wrongly.
        app.add_api_route(
            f"/w/{name}",
            RedirectTo(f"/w/{name}/"),
            methods=["GET"],
            include_in_schema=False,
        )
        app.mount(f"/w/{name}", RevalidatedStaticFiles(directory=WEB_DIR, html=True), name=f"web-{name}")
    app.mount("/", RevalidatedStaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
