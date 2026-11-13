# timetracker.api

FastAPI application exposing the `Tracker` service. All clients (web page,
CLI, panel widget) use these endpoints. Durations are in seconds, times are
ISO 8601.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | active session, time remaining, start defaults, today's totals |
| POST | `/api/sessions` | start a session (`type`, optional `label`, `planned_minutes`, `start` to backdate); with `start` and `end`, record a finished one |
| PATCH | `/api/sessions/{id}` | change a session, including the running one (`type`, `label`, `start`, `end`, `planned_minutes`, `reopen`) |
| DELETE | `/api/sessions/{id}` | delete a session |
| POST | `/api/sessions/end` | end the active session |
| GET | `/api/days/{day}` | sessions and totals for a day (`today` or `YYYY-MM-DD`) |
| GET | `/api/months/{month}` | per-day, per-week and overall totals for a month (`current` or `YYYY-MM`) |
| PUT | `/api/days/{day}` | set the day's target (`target_hours`) |
| POST | `/api/days/{day}/signoff` | sign the day off |

When a session is added or edited, it wins conflicts: sessions it partly
overlaps are trimmed, one it falls inside is split around it, and the request
is refused (409) if it would completely cover another session.
