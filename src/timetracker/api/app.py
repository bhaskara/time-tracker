"""FastAPI application: JSON endpoints over the tracker, plus the alert ticker loop."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, BaseModel, Field

from timetracker.core.accounting import DaySummary, RangeTotals
from timetracker.core.model import DayConfig, Session, SessionType
from timetracker.ticker import AlertTicker
from timetracker.tracker import DayView, MonthView, SessionEdit, SessionView, StatusView, Tracker

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


class TickerLoop:
    """Runs an ``AlertTicker`` repeatedly as an asyncio task.

    Parameters
    ----------
    ticker : AlertTicker
        The ticker to call.
    interval : float
        Seconds between ticks.
    """

    def __init__(self, ticker: AlertTicker, interval: float) -> None:
        self._ticker = ticker
        self._interval = interval

    async def run(self) -> None:
        """Tick forever. A failing tick is logged and the loop continues."""
        while True:
            try:
                await asyncio.to_thread(self._ticker.tick)
            except Exception:
                # One bad tick must not silence all later alerts.
                logger.exception("alert tick failed")
            await asyncio.sleep(self._interval)


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


def create_app(
    tracker: Tracker, ticker: AlertTicker | None = None, tick_interval: float = 1.0
) -> FastAPI:
    """Build the HTTP application.

    Parameters
    ----------
    tracker : Tracker
        Application service the endpoints call.
    ticker : AlertTicker, optional
        If given, it is ticked every ``tick_interval`` seconds while the app runs.
    tick_interval : float
        Seconds between ticks.

    Returns
    -------
    FastAPI
        The application, serving the API under ``/api`` and the web page at
        ``/``. Operations refused by the tracker yield HTTP 409.
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = None
        if ticker is not None:
            task = asyncio.create_task(TickerLoop(ticker, tick_interval).run())
        yield
        if task is not None:
            task.cancel()

    app = FastAPI(title="Time Tracker", lifespan=lifespan)

    @app.get("/api/status")
    def get_status() -> dict:
        """Active session, time remaining, start defaults and today's totals."""
        return status_json(tracker.status())

    @app.post("/api/sessions")
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
                session = tracker.start(kind, request.label, planned, request.start)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @app.patch("/api/sessions/{session_id}")
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
            session = tracker.edit(session_id, changes)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @app.post("/api/sessions/{session_id}/break")
    def break_after(session_id: str) -> dict:
        """Record the break that followed a finished work session."""
        try:
            session = tracker.break_after(session_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict:
        """Delete a session."""
        try:
            session = tracker.delete(session_id)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return session_json(session)

    @app.post("/api/sessions/end")
    def end_session() -> dict:
        """End the active session."""
        try:
            session = tracker.end()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return session_json(session)

    @app.get("/api/days/{day}")
    def get_day(day: str) -> dict:
        """Sessions and totals for a day (``today`` or ``YYYY-MM-DD``)."""
        return day_json(tracker.day(_parse_day(tracker, day)))

    @app.get("/api/months/{month}")
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

    @app.put("/api/days/{day}")
    def put_day(day: str, request: TargetRequest) -> dict:
        """Set a day's target."""
        config = tracker.set_target(
            _parse_day(tracker, day), timedelta(hours=request.target_hours)
        )
        return day_config_json(config)

    @app.post("/api/days/{day}/signoff")
    def sign_off(day: str) -> dict:
        """Sign a day off, ending the active session if it is today."""
        return day_config_json(tracker.sign_off(_parse_day(tracker, day)))

    # Mounted last so it only handles paths the API routes did not match.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
