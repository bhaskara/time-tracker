# time-tracker

Low-friction daily time tracker, pomodoro-like: one active session at a time,
an explicit "what am I doing for the next N minutes", credited-but-capped
breaks, tracked distractions, and daily/weekly records.

Design and accounting rules: https://github.com/bhaskara/time-tracker/issues/1

## Layout

- `src/timetracker/` — the Python package (see its README).
- `tests/` — pytest suite, mirroring the package layout.

## Development

```
uv sync
uv run pytest
```
