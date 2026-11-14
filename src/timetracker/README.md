# timetracker

- `core/` — pure domain model and accounting rules. No I/O.
- `ports.py` — interfaces to the outside world (store, clock, notifier, presence).
- `tracker.py` — application service: load history, apply a core transition, persist.
- `ticker.py` — periodic check that turns due alerts into notifications.
- `adapters/` — concrete ports: SQLite, system clock, desktop notifications, screen-lock presence.
- `api/` — FastAPI app over the tracker.
- `cli/` — the `tt` command, a client of the API.
- `web/` — the browser page served at `/`.
- `backup.py` — consistent database snapshots with pruning.
- `config.py` — optional TOML configuration.
- `server.py` — entry point (`tt-server`), binds to 127.0.0.1.
