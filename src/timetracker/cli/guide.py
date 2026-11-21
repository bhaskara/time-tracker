"""The long-form guide printed by ``tt help``."""

GUIDE = """\
tt - time tracker

One session runs at a time. The server (a background service) keeps the
state; tt, the web page and the panel widget all show and change the same
thing.

SESSION TYPES
  work         Has a label and a planned duration. Counts toward the daily
               target, including time past the planned end. Chimes at the
               planned end and every 5 minutes after.
  break        Counts as work up to min(20% of the work just before it,
               15 min), then ends by itself. Needs work directly before it.
  distraction  Not working, not a real break. Counts against you: its
               duration plus a fixed 10 min switch cost.

STARTING AND STOPPING
  tt start 30 write report     Start work: minutes first, then the label.
  tt start 45                  Same label as last time, 45 minutes.
  tt start                     Repeat the last work label and duration.
  tt break                     Start a break (ends the work session).
  tt distract                  Start a distraction.
  tt end                       End whatever is running.

  Starting anything ends the session that was running.

FIXING THINGS AFTER THE FACT
  tt started 10                The current session really began 10 min ago.
  tt distract --ago 15         "I have been distracted for 15 minutes": the
                               session that was running is cut off there.
  tt start --ago 5 30 review   Work that began 5 minutes ago.
  tt break --ago 20            Left a session running and walked away 20
                               minutes ago: work is cut back, the break
                               takes the credit it earned.

  --ago works with start, break and distract. Editing times,
  labels or types of earlier sessions, deleting them, and adding missed ones
  is done on the web page (select a session, Enter).

LOOKING
  tt                           Same as tt status.
  tt status                    Current session and today's totals.
  tt status --short            One line, for scripts and widgets.
  tt today                     Today's sessions, then the totals.

  "counted" is work plus credited breaks; that is what the target measures.

THE DAY
  tt target 6                  Set today's target to 6 hours (default 8).
  tt note look into layer 12   Append a bullet to today's working memory.
  tt signoff                   Sign off: ends a running work session and
                               stops the idle nudges. The whole working
                               memory carries over to the next day. To choose
                               what carries over, sign off from the web page
                               instead (key s).

  Days run from 2 AM to 2 AM. If no session is running on a day you have
  worked and not signed off, a nudge appears every 10 minutes while the
  screen is unlocked.

OTHER
  tt backup                    Write a dated snapshot of the database to the
                               configured backup folder (--to DIR to choose).
  tt --notify <command>        Also show the result as a desktop
                               notification; for global keyboard shortcuts.
  tt help                      This guide.
  tt <command> --help          Options of one command.

WHERE THINGS ARE
  Web page        http://localhost:8765  (press ? there for its keys)
  Review page     http://localhost:8765/review.html
  Service         systemctl --user status timetracker
  Settings        ~/.config/timetracker/config.toml
  Data            ~/.local/share/timetracker/timetracker.sqlite3
"""
