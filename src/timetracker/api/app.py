"""FastAPI application: JSON endpoints over the tracker, plus the alert ticker loop."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from timetracker.core.model import DayConfig, Session, SessionType
from timetracker.ticker import AlertTicker
from timetracker.tracker import DayView, SessionView, StatusView, Tracker

logger = logging.getLogger(__name__)


class StartRequest(BaseModel):
    """Body of a request to start a session."""

    type: Literal["work", "break", "distraction"]
    label: str | None = None
    planned_minutes: float | None = Field(default=None, gt=0)


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
        The application. Operations refused by the tracker yield HTTP 409.
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
        """Start a session now, ending whatever is active."""
        planned = (
            None if request.planned_minutes is None else timedelta(minutes=request.planned_minutes)
        )
        try:
            session = tracker.start(SessionType(request.type), request.label, planned)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
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

    return app
