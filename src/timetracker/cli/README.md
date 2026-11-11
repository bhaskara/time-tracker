# timetracker.cli

The `tt` command: a thin client of the HTTP API, standard library only.

```
tt status [--short]         current session and today's totals
tt start [MIN] [LABEL...]   start work; omitted values reuse the last ones
tt break                    start a break
tt distract                 start a distraction
tt end                      end the current session
tt today                    list today's sessions
tt target HOURS             set today's target
tt signoff                  sign off for the day
```

`tt --notify <command>` also shows the result as a desktop notification, for
use from global keyboard shortcuts.

- `main.py` — argument parsing, the HTTP client, and output formatting.
