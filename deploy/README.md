# deploy

Running the server automatically.

- `install-backup.sh` — sets up a daily database snapshot (see Backups below).
- `install-service.sh` — installs and starts a systemd user service
  (`timetracker.service`) that runs `tt-server` from this checkout's virtual
  environment at login and restarts it on failure.

```
uv sync                       # make sure .venv exists
deploy/install-service.sh
```

Useful commands afterwards:

```
systemctl --user status timetracker
systemctl --user restart timetracker     # after pulling new code
journalctl --user -u timetracker -f      # logs
systemctl --user disable --now timetracker
```

## The `tt` command

```
uv tool install --editable .     # puts tt in ~/.local/bin
```

Because the install is editable, `tt` follows the checkout; no reinstall is
needed after pulling.

## KDE global shortcuts

To control sessions from any window, bind commands in System Settings →
Shortcuts → Custom Shortcuts → Edit → New → Global Shortcut → Command/URL.
`--notify` shows the result as a short desktop notification, since there is no
terminal to print to. Suggested bindings (pick any free keys):

| Suggested key | Command | Effect |
|---|---|---|
| Meta+Alt+W | `tt --notify start` | start work with the last label and duration |
| Meta+Alt+B | `tt --notify break` | start a break |
| Meta+Alt+D | `tt --notify distract` | start a distraction |
| Meta+Alt+E | `tt --notify end` | end the current session |
| Meta+Alt+S | `tt --notify status` | show what is running and today's totals |
| Meta+Alt+T | `xdg-open http://localhost:8765` | open the day view (to type a new label) |

Use the full path (`~/.local/bin/tt`) if the shortcut does not find `tt`.

## Backups

```
deploy/install-backup.sh ~/Dropbox/backup/timetracker
```

This records the folder as `backup_dir` in `~/.config/timetracker/config.toml`
and installs a systemd user timer (`timetracker-backup.timer`) that runs
`tt backup` every day at 03:00, or at the next login or wake if the machine
was off. It also takes one snapshot straight away.

Each run writes `timetracker-YYYY-MM-DD.sqlite3` using SQLite's online
backup, which gives a consistent copy while the server is running, and keeps
the newest 14 (`backup_keep` in the config). Do not point `db_path` itself at
a synced folder: sync clients can corrupt a live SQLite file.

```
tt backup                                   # take a snapshot now
systemctl --user list-timers timetracker-backup.timer
journalctl --user -u timetracker-backup     # results of past runs
```

To restore: stop the service, copy a snapshot over
`~/.local/share/timetracker/timetracker.sqlite3`, start the service.
