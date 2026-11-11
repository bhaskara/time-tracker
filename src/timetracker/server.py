"""Entry point: wires the real adapters together and serves the API on localhost."""

from dataclasses import replace
from zoneinfo import ZoneInfo

import uvicorn

from timetracker.adapters.kde_presence import ScreenLockPresence
from timetracker.adapters.linux_notifier import LinuxNotifier
from timetracker.adapters.sqlite_store import SqliteStore
from timetracker.adapters.system_clock import SystemClock
from timetracker.api.app import create_app
from timetracker.config import load_config
from timetracker.core.model import Rules
from timetracker.ticker import AlertTicker
from timetracker.tracker import Tracker

# Loopback only: the API has no authentication.
HOST = "127.0.0.1"


def main() -> None:
    """Run the server until interrupted."""
    config = load_config()
    rules = replace(Rules(), timezone=ZoneInfo(config.timezone))
    clock = SystemClock()
    tracker = Tracker(SqliteStore(config.db_path), clock, rules)
    ticker = AlertTicker(tracker, LinuxNotifier(config.sound_file), ScreenLockPresence(), clock)
    uvicorn.run(create_app(tracker, ticker), host=HOST, port=config.port)


if __name__ == "__main__":
    main()
