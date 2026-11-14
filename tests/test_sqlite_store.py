"""Tests for the SQLite store adapter."""

import sqlite3

from datetime import date, timedelta

import pytest

from timetracker.adapters.sqlite_store import MIGRATIONS, SqliteStore, migrate
from timetracker.core.model import DayConfig, DayNotes, Session, SessionType

from .conftest import T0


def mk(sid: str, start: float, end: float | None, kind=SessionType.WORK) -> Session:
    """Session with times in minutes after T0."""
    return Session(
        id=sid,
        type=kind,
        start=T0 + timedelta(minutes=start),
        end=None if end is None else T0 + timedelta(minutes=end),
        label="x" if kind is SessionType.WORK else "",
        planned=timedelta(minutes=25) if kind is SessionType.WORK else None,
    )


def test_round_trip_preserves_sessions(store):
    """Sessions come back equal to what was written, ordered by start."""
    a, b = mk("a", 0, 25), mk("b", 25, None, SessionType.BREAK)
    store.write_sessions([b, a])
    assert store.load_sessions(T0) == (a, b)


def test_upsert_replaces_and_delete_removes(store):
    """Writing an existing id replaces it; deletes remove rows."""
    store.write_sessions([mk("a", 0, None), mk("z", -60, -30)])
    store.write_sessions([mk("a", 0, 10)], delete_ids=["z"])
    assert store.load_sessions(T0 - timedelta(days=1)) == (mk("a", 0, 10),)


def test_load_filters_by_overlap(store):
    """Only sessions overlapping the window are returned; active ones always overlap later windows."""
    old, mid, active = mk("old", -600, -590), mk("mid", 0, 25), mk("act", 30, None)
    store.write_sessions([old, mid, active])
    assert store.load_sessions(T0) == (mid, active)
    assert store.load_sessions(T0, T0 + timedelta(minutes=10)) == (mid,)
    assert store.load_sessions(T0 + timedelta(days=3)) == (active,)


def test_last_work_session(store):
    """The latest work session is found regardless of later non-work sessions."""
    assert store.last_work_session() is None
    store.write_sessions([mk("a", 0, 25), mk("b", 30, 55), mk("c", 55, 60, SessionType.BREAK)])
    assert store.last_work_session().id == "b"


def test_day_config_round_trip(store):
    """Day settings round-trip, including the sign-off time."""
    day = date(2026, 11, 11)
    assert store.get_day(day) is None
    config = DayConfig(day=day, target=timedelta(hours=6), signed_off_at=T0)
    store.put_day(config)
    assert store.get_day(day) == config


def test_persists_across_connections(tmp_path):
    """Data written to a file is visible to a new store on the same file."""
    path = tmp_path / "sub" / "tt.sqlite3"
    SqliteStore(path).write_sessions([mk("a", 0, 25)])
    assert SqliteStore(path).load_sessions(T0) == (mk("a", 0, 25),)


def test_migrations_apply_incrementally_and_keep_data(tmp_path):
    """A later migration (e.g. adding a category column) upgrades an existing database in place."""
    path = tmp_path / "tt.sqlite3"
    SqliteStore(path).write_sessions([mk("a", 0, 25)])
    db = sqlite3.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    migrate(db, (*MIGRATIONS, "ALTER TABLE sessions ADD COLUMN category TEXT;"))
    assert db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) + 1
    assert db.execute("SELECT id, category FROM sessions").fetchall() == [("a", None)]
    assert SqliteStore(":memory:").load_sessions(T0) == ()


def test_newer_database_is_refused(tmp_path):
    """Opening a database from a newer program version fails loudly."""
    path = tmp_path / "tt.sqlite3"
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    db.close()
    with pytest.raises(RuntimeError, match="newer"):
        SqliteStore(path)


def test_notes_round_trip_and_latest_before(store):
    """Notes round-trip, and the latest earlier day's notes can be found."""
    day = date(2026, 11, 11)
    assert store.get_notes(day) is None and store.latest_notes_before(day) is None
    monday = DayNotes(date(2026, 11, 9), body="mon", seed_next="", updated_at=T0)
    tuesday = DayNotes(date(2026, 11, 10), body="# tue\n- [ ] x", updated_at=T0)
    store.put_notes(monday)
    store.put_notes(tuesday)
    assert store.get_notes(date(2026, 11, 9)) == monday
    assert store.latest_notes_before(day) == tuesday
    assert store.latest_notes_before(date(2026, 11, 10)) == monday
    with pytest.raises(ValueError, match="updated_at"):
        store.put_notes(DayNotes(day, body="x"))


def test_existing_database_gains_notes_table(tmp_path):
    """A database created before working memory existed is upgraded on open, keeping its data."""
    path = tmp_path / "tt.sqlite3"
    db = sqlite3.connect(path)
    migrate(db, MIGRATIONS[:1])
    db.close()
    old = SqliteStore.__new__(SqliteStore)  # write a session through the v1 schema
    old._db = sqlite3.connect(path)
    old.write_sessions([mk("a", 0, 25)])
    old._db.close()
    store = SqliteStore(path)
    assert store.load_sessions(T0) == (mk("a", 0, 25),)
    store.put_notes(DayNotes(date(2026, 11, 11), body="x", updated_at=T0))
    assert store.get_notes(date(2026, 11, 11)).body == "x"
