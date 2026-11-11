# time-tracker

Low-friction daily time tracker, pomodoro-like: one active session at a time,
an explicit "what am I doing for the next N minutes", credited-but-capped
breaks, tracked distractions, and daily/weekly records.

Design and accounting rules: https://github.com/bhaskara/time-tracker/issues/1

## Layout

- `src/timetracker/` — the Python package (see its README).
- `tests/` — pytest suite, mirroring the package layout.
- `deploy/` — systemd user service installer.

## Running

```
uv run tt-server
```

To run it automatically at login instead, use `deploy/install-service.sh`
(see `deploy/README.md`).

Serves the web page and API on http://127.0.0.1:8765 (loopback only) and sends desktop
notifications with a chime. Data lives in
`~/.local/share/timetracker/timetracker.sqlite3`. Optional settings go in
`~/.config/timetracker/config.toml` (`port`, `db_path`, `sound_file`,
`timezone`). Endpoints are listed in `src/timetracker/api/README.md`.

```
curl -X POST localhost:8765/api/sessions -H 'content-type: application/json' \
     -d '{"type": "work", "label": "write report", "planned_minutes": 30}'
curl localhost:8765/api/status
curl -X POST localhost:8765/api/sessions/end
```

## Development

```
uv sync
uv run pytest
```
