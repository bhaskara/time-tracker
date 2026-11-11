# timetracker.adapters

Concrete implementations of the interfaces in `ports.py`. All I/O lives here.

- `sqlite_store.py` — `Store` on SQLite; timestamps stored as UTC text.
- `system_clock.py` — `Clock` on the system time.
- `linux_notifier.py` — `Notifier` using `notify-send` and `pw-play`.
- `kde_presence.py` — `Presence` from the KDE screen-lock state.
