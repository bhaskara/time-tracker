# timetracker.api

FastAPI application exposing the `Tracker` service. All clients (web page,
CLI, panel widget) use these endpoints. Durations are in seconds, times are
ISO 8601.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | active session, time remaining, start defaults, today's totals |
| POST | `/api/sessions` | start a session (`type`, optional `label`, `planned_minutes`) |
| POST | `/api/sessions/end` | end the active session |
| GET | `/api/days/{day}` | sessions and totals for a day (`today` or `YYYY-MM-DD`) |
| PUT | `/api/days/{day}` | set the day's target (`target_hours`) |
| POST | `/api/days/{day}/signoff` | sign the day off |
