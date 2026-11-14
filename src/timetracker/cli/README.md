# timetracker.cli

The `tt` command: a thin client of the HTTP API, standard library only.

```
tt                          same as tt status
tt status [--short]         current session and today's totals
tt start [MIN] [LABEL...]   start work; omitted values reuse the last ones
tt break                    start a break
tt distract                 start a distraction
tt end                      end the current session
tt started MIN              the current session really began MIN minutes ago
tt today                    list today's sessions
tt target HOURS             set today's target
tt signoff                  sign off for the day
tt note TEXT...             append a bullet to today's working memory
```

`start`, `break` and `distract` take `--ago MIN` to backdate the start; the
session that was running at that time is cut there (for example
`tt distract --ago 15`).

`tt --notify <command>` also shows the result as a desktop notification, for
use from global keyboard shortcuts.

- `main.py` — argument parsing, the HTTP client, and output formatting.
