"""Database snapshots: consistent copies of the SQLite file, safe while the server runs."""

import sqlite3
from datetime import date
from pathlib import Path

PREFIX = "timetracker-"
SUFFIX = ".sqlite3"


def snapshot_prefix(workspace: str | None = None) -> str:
    """File name prefix of a workspace's snapshots; None is the default workspace."""
    return PREFIX if workspace is None else f"{PREFIX}{workspace}-"


def snapshot_name(day: date, workspace: str | None = None) -> str:
    """File name of the snapshot of ``workspace`` taken on ``day``."""
    return f"{snapshot_prefix(workspace)}{day.isoformat()}{SUFFIX}"


def snapshots(dest_dir: Path, workspace: str | None = None) -> list[Path]:
    """Return the snapshot files of ``workspace`` in ``dest_dir``, oldest first."""
    return sorted(dest_dir.glob(f"{snapshot_prefix(workspace)}????-??-??{SUFFIX}"))


def backup_database(
    db_path: Path, dest_dir: Path, day: date, keep: int, workspace: str | None = None
) -> Path:
    """Write a snapshot of the database and prune old snapshots.

    Uses SQLite's online backup, so the copy is consistent even if the server
    is writing at the same time. The snapshot is written to a temporary name
    and renamed, so a sync client never sees a half-written file under the
    final name.

    Parameters
    ----------
    db_path : Path
        The live database. Must exist.
    dest_dir : Path
        Folder for snapshots; created if missing.
    day : date
        Date used in the snapshot's name. A snapshot already taken on that
        date is replaced.
    keep : int
        Number of most recent snapshots to keep; older ones are deleted.
        Must be at least 1.
    workspace : str, optional
        Name of the workspace the database belongs to; None for the default
        one. It becomes part of the file name, and only that workspace's
        snapshots are pruned.

    Returns
    -------
    Path
        The snapshot file, which has passed SQLite's integrity check.

    Raises
    ------
    FileNotFoundError
        If ``db_path`` does not exist.
    ValueError
        If ``keep`` is less than 1.
    RuntimeError
        If the snapshot fails the integrity check; it is deleted and existing
        snapshots are left alone.
    """
    if keep < 1:
        raise ValueError("keep must be at least 1")
    if not db_path.is_file():
        raise FileNotFoundError(f"database not found: {db_path}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / snapshot_name(day, workspace)
    partial = target.with_name(target.name + ".partial")
    partial.unlink(missing_ok=True)

    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    copy = sqlite3.connect(partial)
    try:
        source.backup(copy)
        result = copy.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        copy.close()
        source.close()
    if result != "ok":
        partial.unlink()
        raise RuntimeError(f"snapshot failed its integrity check: {result}")
    partial.replace(target)

    for old in snapshots(dest_dir, workspace)[:-keep]:
        old.unlink()
    return target
