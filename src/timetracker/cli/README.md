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
tt help                     a longer guide with examples
tt note TEXT...             append a bullet to today's working memory
tt backup [--to DIR]        write a dated snapshot of every workspace's database (see deploy/README.md)
tt workspaces               list the workspaces and what is running in each
tt -w NAME <command>        act on another workspace, e.g. tt -w personal start 40 cook dinner
```

Without `-w`, the workspace is `$TT_WORKSPACE` if set, otherwise `work`.

`start`, `break` and `distract` take `--ago MIN` to backdate the start; the
session that was running at that time is cut there (for example
`tt distract --ago 15`).

`tt --notify <command>` also shows the result as a desktop notification, for
use from global keyboard shortcuts.

- `main.py` — argument parsing, the HTTP client, and output formatting.
- `guide.py` — the text printed by `tt help`.
