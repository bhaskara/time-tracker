"""SQLite store adapter.

Timestamps are stored as fixed-format UTC ISO strings, so text comparison in
SQL orders them correctly.
"""

import sqlite3
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from timetracker.core.model import DayConfig, Session, SessionType

# Schema changes are appended here as further scripts; a database records how
# many it has applied in ``PRAGMA user_version``. New session attributes (for
# example a work subcategory column or a session_tags table) are added this way.
MIGRATIONS = (
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id        TEXT PRIMARY KEY,
        type      TEXT NOT NULL,
        start     TEXT NOT NULL,
        end       TEXT,
        label     TEXT NOT NULL,
        planned_s REAL
    );
    CREATE INDEX IF NOT EXISTS sessions_start ON sessions (start);
    CREATE TABLE IF NOT EXISTS days (
        day           TEXT PRIMARY KEY,
        target_s      REAL NOT NULL,
        signed_off_at TEXT
    );
    """,
)


def migrate(db: sqlite3.Connection, migrations: tuple[str, ...] = MIGRATIONS) -> None:
    """Bring a database up to the latest schema.

    Parameters
    ----------
    db : sqlite3.Connection
        Open connection.
    migrations : tuple[str, ...]
        SQL scripts in order; script ``i`` takes the schema from version
        ``i`` to ``i + 1``.

    Raises
    ------
    RuntimeError
        If the database was written by a newer version of the program.
    """
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > len(migrations):
        raise RuntimeError(
            f"database schema version {version} is newer than this program supports "
            f"({len(migrations)})"
        )
    for target, script in enumerate(migrations[version:], start=version + 1):
        db.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {target};\nCOMMIT;")


_COLUMNS = "id, type, start, end, label, planned_s"


def _to_text(t: datetime | None) -> str | None:
    """Encode an aware datetime as UTC text."""
    return None if t is None else t.astimezone(UTC).isoformat(timespec="microseconds")


def _from_text(text: str | None) -> datetime | None:
    """Decode UTC text back into an aware datetime."""
    return None if text is None else datetime.fromisoformat(text)


def _session(row: tuple) -> Session:
    """Build a session from a database row."""
    sid, type_, start, end, label, planned_s = row
    return Session(
        id=sid,
        type=SessionType(type_),
        start=_from_text(start),
        end=_from_text(end),
        label=label,
        planned=None if planned_s is None else timedelta(seconds=planned_s),
    )


class SqliteStore:
    """Sessions and day settings in one SQLite file.

    The connection may be used from any thread, but callers must serialise
    access themselves (``Tracker`` does).

    Parameters
    ----------
    path : Path or str
        Database file; parent directories are created. ``":memory:"`` gives
        a throwaway database.
    """

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        migrate(self._db)

    def load_sessions(self, lo: datetime, hi: datetime | None = None) -> tuple[Session, ...]:
        """Return sessions overlapping ``[lo, hi)`` ordered by start.

        An active session counts as extending forever; ``hi=None`` means no
        upper bound.
        """
        query = f"SELECT {_COLUMNS} FROM sessions WHERE (end IS NULL OR end >= ?)"
        params = [_to_text(lo)]
        if hi is not None:
            query += " AND start < ?"
            params.append(_to_text(hi))
        rows = self._db.execute(query + " ORDER BY start, end IS NULL, end", params).fetchall()
        return tuple(_session(r) for r in rows)

    def write_sessions(self, upserts: Sequence[Session], delete_ids: Sequence[str] = ()) -> None:
        """Atomically insert or replace ``upserts`` (by id) and delete ``delete_ids``."""
        with self._db:
            self._db.executemany("DELETE FROM sessions WHERE id = ?", [(i,) for i in delete_ids])
            self._db.executemany(
                f"INSERT OR REPLACE INTO sessions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        s.id,
                        s.type.value,
                        _to_text(s.start),
                        _to_text(s.end),
                        s.label,
                        None if s.planned is None else s.planned.total_seconds(),
                    )
                    for s in upserts
                ],
            )

    def get_session(self, session_id: str) -> Session | None:
        """Return the session with this id, or None if there is none."""
        row = self._db.execute(
            f"SELECT {_COLUMNS} FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return None if row is None else _session(row)

    def last_work_session(self) -> Session | None:
        """Return the work session with the latest start, if any."""
        row = self._db.execute(
            f"SELECT {_COLUMNS} FROM sessions WHERE type = ? ORDER BY start DESC LIMIT 1",
            (SessionType.WORK.value,),
        ).fetchone()
        return None if row is None else _session(row)

    def get_day(self, day: date) -> DayConfig | None:
        """Return the stored settings for ``day``, or None if never set."""
        row = self._db.execute(
            "SELECT target_s, signed_off_at FROM days WHERE day = ?", (day.isoformat(),)
        ).fetchone()
        if row is None:
            return None
        return DayConfig(
            day=day, target=timedelta(seconds=row[0]), signed_off_at=_from_text(row[1])
        )

    def put_day(self, config: DayConfig) -> None:
        """Insert or replace the settings for ``config.day``."""
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO days (day, target_s, signed_off_at) VALUES (?, ?, ?)",
                (
                    config.day.isoformat(),
                    config.target.total_seconds(),
                    _to_text(config.signed_off_at),
                ),
            )
