"""The ``tt`` command: parses arguments, calls the server's HTTP API, prints the result."""

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from timetracker.backup import backup_database
from timetracker.config import load_config


class ApiError(Exception):
    """The server refused a request or could not be reached."""


class Client(Protocol):
    """Something that can perform API calls."""

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        """Perform a request and return the decoded JSON, raising ``ApiError`` on failure."""
        ...


class ApiClient:
    """HTTP client for the tracker server.

    Parameters
    ----------
    base_url : str
        Server address, e.g. ``http://127.0.0.1:8765``.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        """Perform a request.

        Parameters
        ----------
        method : str
            HTTP method.
        path : str
            Path starting with ``/api``.
        body : dict, optional
            JSON body.

        Returns
        -------
        dict
            Decoded JSON response.

        Raises
        ------
        ApiError
            If the server is unreachable or answers with an error status; the
            message carries the server's stated reason.
        """
        request = urllib.request.Request(
            self._base_url + path,
            method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            raise ApiError(error_detail(e.read())) from e
        except urllib.error.URLError as e:
            raise ApiError(
                f"cannot reach the server at {self._base_url} ({e.reason}); "
                "try: systemctl --user start timetracker"
            ) from e


def error_detail(payload: bytes) -> str:
    """Extract the human-readable reason from an error response body."""
    try:
        detail = json.loads(payload)["detail"]
    except (ValueError, KeyError, TypeError):
        return payload.decode(errors="replace")
    return detail if isinstance(detail, str) else json.dumps(detail)


def clock(seconds: float) -> str:
    """Format seconds as ``m:ss`` or ``h:mm:ss``."""
    s = max(0, int(seconds))
    h, rest = divmod(s, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def duration(seconds: float) -> str:
    """Format seconds as a rounded duration such as ``45s``, ``7m`` or ``2h 05m``."""
    if 0 < seconds < 60:
        return f"{round(seconds)}s"
    m = round(seconds / 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def time_of_day(iso: str) -> str:
    """Format an ISO timestamp as local ``H:MM``."""
    local = datetime.fromisoformat(iso).astimezone()
    return f"{local.hour}:{local.minute:02d}"


def format_now(status: dict) -> str:
    """Describe the current session in one line.

    Parameters
    ----------
    status : dict
        Response of ``GET /api/status``.

    Returns
    -------
    str
        E.g. ``work 12:34 left · write report``, ``work +3:10 over · write
        report``, ``break 4:00 left``, ``distraction 2:15``, ``idle 12m`` or
        ``signed off``.
    """
    active = status["active"]
    if active is None:
        today = status["today"]
        if today["signed_off_at"]:
            return "signed off"
        if not today["sessions"]:
            return "idle"
        last_end = datetime.fromisoformat(today["sessions"][-1]["end"])
        idle = (datetime.fromisoformat(status["now"]) - last_end).total_seconds()
        return f"idle {duration(idle)}"
    label = f" · {active['label']}" if active["label"] else ""
    if active["type"] == "distraction":
        return f"distraction {clock(status['elapsed_s'])}{label}"
    remaining = status["remaining_s"]
    if remaining < 0:
        return f"{active['type']} +{clock(-remaining)} over{label}"
    return f"{active['type']} {clock(remaining)} left{label}"


def format_totals(day: dict) -> str:
    """Summarise a day's totals in one line."""
    return (
        f"today: {duration(day['counted_s'])} counted of {duration(day['target_s'])} "
        f"({round(100 * day['progress'])}%) · distraction {duration(day['distraction_s'])}"
    )


def format_sessions(day: dict) -> str:
    """List a day's sessions, oldest first, one per line, followed by the totals."""
    lines = []
    for s in day["sessions"]:
        end = time_of_day(s["end"]) if s["end"] else "now"
        span = f"{time_of_day(s['start'])}–{end}"
        lines.append(f"{span:<13} {s['type']:<11} {duration(s['duration_s']):>7}  {s['label']}".rstrip())
    if not lines:
        lines.append("no sessions")
    return "\n".join([*lines, format_totals(day)])


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for ``tt``."""
    parser = argparse.ArgumentParser(prog="tt", description="Time tracker client.")
    parser.add_argument(
        "--notify", action="store_true", help="also show the result as a desktop notification"
    )
    # No command means "status".
    commands = parser.add_subparsers(dest="command")
    status = commands.add_parser("status", help="current session and today's totals")
    status.add_argument("--short", action="store_true", help="one line, for widgets")
    start = commands.add_parser("start", help="start a work session")
    start.add_argument(
        "words",
        nargs="*",
        metavar="[MINUTES] [LABEL...]",
        help="duration and label; whatever is omitted reuses the last value",
    )
    brk = commands.add_parser("break", help="start a break")
    distract = commands.add_parser("distract", help="start a distraction")
    for starter in (start, brk, distract):
        starter.add_argument(
            "--ago",
            type=float,
            metavar="MIN",
            help="the session really began MIN minutes ago; what was running then is cut there",
        )
    started = commands.add_parser(
        "started", help="say the current session really began MIN minutes ago"
    )
    started.add_argument("minutes", type=float, metavar="MIN")
    commands.add_parser("end", help="end the current session")
    commands.add_parser("today", help="list today's sessions")
    target = commands.add_parser("target", help="set today's target")
    target.add_argument("hours", type=float)
    commands.add_parser("signoff", help="sign off for the day")
    backup = commands.add_parser(
        "backup", help="write a snapshot of the database to the backup folder"
    )
    backup.add_argument("--to", type=Path, metavar="DIR", help="folder (default: backup_dir in the config)")
    backup.add_argument("--db", type=Path, metavar="FILE", help="database (default: db_path in the config)")
    backup.add_argument("--keep", type=int, metavar="N", help="snapshots to keep (default: backup_keep)")
    note = commands.add_parser("note", help="append a bullet to today's working memory")
    note.add_argument("text", nargs="+")
    return parser


def start_body(words: Sequence[str]) -> dict:
    """Turn ``tt start`` arguments into a request body.

    Parameters
    ----------
    words : Sequence[str]
        Arguments after ``start``. A leading number is the duration in
        minutes; the remaining words form the label.

    Returns
    -------
    dict
        Body for ``POST /api/sessions`` with only the values that were given.
    """
    body: dict = {"type": "work"}
    rest = list(words)
    if rest:
        try:
            body["planned_minutes"] = float(rest[0])
        except ValueError:
            pass
        else:
            rest = rest[1:]
    if rest:
        body["label"] = " ".join(rest)
    return body


def minutes_ago(client: Client, minutes: float) -> str:
    """Return the ISO timestamp ``minutes`` before the server's current time."""
    now = datetime.fromisoformat(client.call("GET", "/api/status")["now"])
    return (now - timedelta(minutes=minutes)).isoformat()


def run_backup(args: argparse.Namespace) -> str:
    """Write a database snapshot. Works on the files directly, without the server.

    Raises
    ------
    ApiError
        If no backup folder is given or configured, or the snapshot fails.
    """
    config = load_config()
    dest = args.to or config.backup_dir
    if dest is None:
        raise ApiError("no backup folder: pass --to DIR or set backup_dir in the config file")
    try:
        target = backup_database(
            args.db or config.db_path, dest, date.today(), args.keep or config.backup_keep
        )
    except (OSError, ValueError, RuntimeError) as e:
        raise ApiError(f"backup failed: {e}") from e
    return f"backed up to {target} ({target.stat().st_size // 1024} KB)"


def execute(args: argparse.Namespace, client: Client) -> str:
    """Carry out a parsed command (``status`` if none was given) and return the text to print.

    Raises
    ------
    ApiError
        If the server refuses the operation or cannot be reached.
    """
    command = args.command or "status"
    if command == "status":
        status = client.call("GET", "/api/status")
        now = format_now(status)
        short = getattr(args, "short", False)
        return now if short else f"{now}\n{format_totals(status['today'])}"
    if command == "today":
        return format_sessions(client.call("GET", "/api/days/today"))
    if command == "target":
        client.call("PUT", "/api/days/today", {"target_hours": args.hours})
        return format_totals(client.call("GET", "/api/days/today"))
    if command == "backup":
        return run_backup(args)
    if command == "note":
        client.call("POST", "/api/days/today/notes/append", {"text": " ".join(args.text)})
        return "noted"
    if command == "signoff":
        client.call("POST", "/api/days/today/signoff")
        return f"signed off\n{format_totals(client.call('GET', '/api/days/today'))}"
    if command == "end":
        ended = client.call("POST", "/api/sessions/end")
        return f"ended {ended['type']}\n{format_totals(client.call('GET', '/api/days/today'))}"
    if command == "started":
        active = client.call("GET", "/api/status")["active"]
        if active is None:
            raise ApiError("no active session")
        client.call(
            "PATCH", f"/api/sessions/{active['id']}", {"start": minutes_ago(client, args.minutes)}
        )
        return format_now(client.call("GET", "/api/status"))
    if command == "start":
        body = start_body(args.words)
    elif command == "break":
        body = {"type": "break"}
    else:
        body = {"type": "distraction"}
    if args.ago is not None:
        body["start"] = minutes_ago(client, args.ago)
    client.call("POST", "/api/sessions", body)
    return format_now(client.call("GET", "/api/status"))


def run(argv: Sequence[str], client: Client) -> tuple[int, str]:
    """Run the CLI against a client.

    Parameters
    ----------
    argv : Sequence[str]
        Arguments without the program name. ``--notify`` is accepted but
        acted on by ``main``.
    client : Client
        Performs the API calls.

    Returns
    -------
    tuple[int, str]
        Exit code (0 on success, 1 if the server refused or was unreachable)
        and the text to show.
    """
    args = build_parser().parse_args(argv)
    try:
        return 0, execute(args, client)
    except ApiError as e:
        return 1, f"error: {e}"


def main() -> None:
    """Entry point for the ``tt`` command."""
    argv = sys.argv[1:]
    client = ApiClient(f"http://127.0.0.1:{load_config().port}")
    code, text = run(argv, client)
    print(text, file=sys.stderr if code else sys.stdout)
    if "--notify" in argv:
        subprocess.run(
            ["notify-send", "--app-name", "Time Tracker", "--expire-time", "4000", *text.split("\n", 1)],
            check=False,
        )
    sys.exit(code)


if __name__ == "__main__":
    main()
