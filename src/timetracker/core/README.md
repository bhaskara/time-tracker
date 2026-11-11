# timetracker.core

Pure functions over immutable session records. Nothing here reads a clock,
a database or the network; "now" is always passed in.

- `model.py` — `Session`, `SessionType`, `Rules` (all tunable constants).
- `accounting.py` — break cap, day boundaries, daily totals, current status.
- `transitions.py` — starting and ending sessions, invariant validation.
- `alerts.py` — which chimes and nudges are due.

Only raw session facts (type, label, planned duration, start, end) are
stored. Break credit, distraction cost and totals are always derived, so
changing a rule re-computes history.
