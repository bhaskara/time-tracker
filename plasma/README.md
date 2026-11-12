# plasma

KDE Plasma 5 panel widget showing the current session.

- `org.timetracker.panel/` — the widget package:
  - `metadata.json` — package description.
  - `contents/ui/main.qml` — polls `http://127.0.0.1:8765/api/status` every
    5 s and shows one coloured line; click opens the web page.
  - `contents/code/format.js` — turns the status into the text shown.
- `install.sh` — installs or upgrades the widget for the current user.

```
plasma/install.sh
```

Then right-click the panel → Add Widgets → search "Time Tracker" and drag it
onto the panel. To try it in a window without touching the panel:
`plasmawindowed org.timetracker.panel`.

What it shows (minutes only):

| State | Text |
|---|---|
| Work | `15m left · label` |
| Past the planned end | `time's up · label`, then `+3m over · label` |
| Break | `break 6m left` |
| Distraction | `distraction 7m` |
| Nothing running | `idle 12m` (or `no session` before the first one) |
| Signed off | `signed off` |
| Server not running | `tracker offline` |

The tooltip shows the full label and today's totals.
