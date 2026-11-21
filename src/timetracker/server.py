"""Entry point: wires the real adapters together and serves the API on localhost."""

from dataclasses import replace
from datetime import timedelta
from zoneinfo import ZoneInfo

import uvicorn

from timetracker.adapters.kde_presence import ScreenLockPresence
from timetracker.adapters.linux_notifier import LinuxNotifier
from timetracker.adapters.sqlite_store import SqliteStore
from timetracker.adapters.system_clock import SystemClock
from timetracker.api.app import create_app
from timetracker.config import DEFAULT_WORKSPACE, Config, load_config
from timetracker.core.model import Rules
from timetracker.ticker import AlertTicker
from timetracker.tracker import Tracker
from timetracker.workspaces import Workspace, Workspaces

# Loopback only: the API has no authentication.
HOST = "127.0.0.1"


def build_workspaces(config: Config) -> Workspaces:
    """Open every configured workspace's database and wire its tracker and ticker.

    Parameters
    ----------
    config : Config
        Loaded settings.

    Returns
    -------
    Workspaces
        One workspace per ``config.all_workspaces()`` entry, the default
        first. Databases are created if missing. Workspaces other than the
        default label their notifications with their name.
    """
    clock = SystemClock()
    notifier = LinuxNotifier(config.sound_file)
    presence = ScreenLockPresence()
    base_rules = replace(Rules(), timezone=ZoneInfo(config.timezone))
    built = []
    for settings in config.all_workspaces():
        rules = base_rules
        if settings.target_hours is not None:
            rules = replace(rules, default_target=timedelta(hours=settings.target_hours))
        tracker = Tracker(SqliteStore(settings.db_path), clock, rules)
        ticker = AlertTicker(
            tracker,
            notifier,
            presence,
            clock,
            alert_popups=config.alert_popups,
            idle_nudge=settings.idle_nudge,
            label="" if settings.name == DEFAULT_WORKSPACE else settings.name,
        )
        built.append(Workspace(settings.name, tracker, ticker))
    return Workspaces(built)


def main() -> None:
    """Run the server until interrupted."""
    config = load_config()
    # No access log: the web page polls every few seconds.
    uvicorn.run(create_app(build_workspaces(config)), host=HOST, port=config.port, access_log=False)


if __name__ == "__main__":
    main()
