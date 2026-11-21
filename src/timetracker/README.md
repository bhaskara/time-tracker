# timetracker

- `core/` — pure domain model and accounting rules. No I/O.
- `ports.py` — interfaces to the outside world (store, clock, notifier, presence).
- `tracker.py` — application service: load history, apply a core transition, persist.
- `ticker.py` — periodic check that turns due alerts into notifications.
- `workspaces.py` — the set of independent trackers (work, personal, ...) served
  together, and the little coordination between them: one running session
  overall, no idle nudge while another workspace is busy.
- `adapters/` — concrete ports: SQLite, system clock, desktop notifications, screen-lock presence.
- `api/` — FastAPI app over each workspace's tracker.
- `cli/` — the `tt` command, a client of the API.
- `web/` — the browser pages served at `/` and `/w/<name>/`.
- `backup.py` — consistent database snapshots with pruning.
- `config.py` — optional TOML configuration, including extra workspaces.
- `server.py` — entry point (`tt-server`), binds to 127.0.0.1.
