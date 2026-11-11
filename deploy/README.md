# deploy

Running the server automatically.

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
