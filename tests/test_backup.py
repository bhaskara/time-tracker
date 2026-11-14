"""Tests for database snapshots."""

import sqlite3
from datetime import date, timedelta

import pytest

from timetracker.adapters.sqlite_store import SqliteStore
from timetracker.backup import backup_database, snapshots
from timetracker.cli.main import run
from timetracker.core.model import Session, SessionType

from .conftest import T0

DAY = date(2026, 11, 14)


@pytest.fixture
def db_path(tmp_path):
    """A database file with one session, still open for writing as the server would have it."""
    path = tmp_path / "live" / "tt.sqlite3"
    store = SqliteStore(path)
    store.write_sessions(
        [Session("a", SessionType.WORK, T0, T0 + timedelta(minutes=25), "task", timedelta(minutes=25))]
    )
    return path


def test_snapshot_is_a_readable_copy(db_path, tmp_path):
    """The snapshot opens as a database with the same sessions."""
    target = backup_database(db_path, tmp_path / "backups", DAY, keep=3)
    assert target.name == "timetracker-2026-11-14.sqlite3"
    assert SqliteStore(target).load_sessions(T0)[0].label == "task"
    assert not list((tmp_path / "backups").glob("*.partial"))


def test_same_day_snapshot_is_replaced(db_path, tmp_path):
    """A second backup on the same date overwrites the first, picking up new data."""
    dest = tmp_path / "backups"
    backup_database(db_path, dest, DAY, keep=3)
    SqliteStore(db_path).write_sessions(
        [Session("b", SessionType.DISTRACTION, T0 + timedelta(minutes=30), T0 + timedelta(minutes=40))]
    )
    target = backup_database(db_path, dest, DAY, keep=3)
    assert len(snapshots(dest)) == 1
    assert sqlite3.connect(target).execute("SELECT count(*) FROM sessions").fetchone()[0] == 2


def test_old_snapshots_are_pruned(db_path, tmp_path):
    """Only the newest `keep` snapshots remain; other files are untouched."""
    dest = tmp_path / "backups"
    dest.mkdir()
    (dest / "notes.txt").write_text("keep me")
    for offset in range(5):
        backup_database(db_path, dest, DAY + timedelta(days=offset), keep=3)
    assert [p.name for p in snapshots(dest)] == [
        "timetracker-2026-11-16.sqlite3",
        "timetracker-2026-11-17.sqlite3",
        "timetracker-2026-11-18.sqlite3",
    ]
    assert (dest / "notes.txt").exists()


def test_missing_database_and_bad_keep(tmp_path, db_path):
    """A missing database or a keep below one is an error and writes nothing."""
    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "nope.sqlite3", tmp_path / "backups", DAY, keep=3)
    with pytest.raises(ValueError):
        backup_database(db_path, tmp_path / "backups", DAY, keep=0)
    assert not (tmp_path / "backups").exists()


def test_cli_backup(db_path, tmp_path):
    """`tt backup --to DIR --db FILE` writes a snapshot; a missing database exits non-zero."""
    dest = tmp_path / "out"
    code, text = run(["backup", "--to", str(dest), "--db", str(db_path)], client=None)
    assert code == 0 and text.startswith(f"backed up to {dest}")
    assert len(snapshots(dest)) == 1
    code, text = run(["backup", "--to", str(dest), "--db", str(tmp_path / "nope")], client=None)
    assert code == 1 and "backup failed" in text
