"""Server configuration, optionally read from a TOML file."""

import os
import re
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path


def _xdg(variable: str, fallback: str) -> Path:
    """Resolve an XDG base directory."""
    return Path(os.environ.get(variable) or Path.home() / fallback)


DEFAULT_CONFIG_PATH = _xdg("XDG_CONFIG_HOME", ".config") / "timetracker" / "config.toml"

# Name of the workspace that every un-prefixed URL and plain ``tt`` command uses.
DEFAULT_WORKSPACE = "work"
_WORKSPACE_NAME = re.compile(r"[a-z][a-z0-9-]*")
_WORKSPACE_KEYS = {"db_path", "target_hours", "idle_nudge"}


@dataclass(frozen=True)
class WorkspaceConfig:
    """Settings of one workspace: an independent set of sessions, days and notes.

    Attributes
    ----------
    name : str
        Short lower-case name used in URLs (``/w/<name>/``) and ``tt -w <name>``.
    db_path : Path
        The workspace's own SQLite database file.
    target_hours : float or None
        Default daily target in hours; None means the built-in default.
    idle_nudge : bool
        Whether the "no session running" nudge is sent for this workspace.
    """

    name: str
    db_path: Path
    target_hours: float | None = None
    idle_nudge: bool = False


@dataclass(frozen=True)
class Config:
    """Server settings.

    Attributes
    ----------
    port : int
        TCP port on 127.0.0.1.
    db_path : Path
        SQLite database file of the default (``work``) workspace.
    sound_file : Path
        Chime played with notifications.
    timezone : str
        IANA zone in which the 2 AM day boundary is evaluated.
    alert_popups : bool
        Whether time's-up, overrun and break-over alerts show a desktop
        pop-up in addition to the chime.
    backup_dir : Path or None
        Folder where ``tt backup`` writes database snapshots; None if not
        configured.
    backup_keep : int
        Number of most recent snapshots to keep (per workspace).
    workspaces : tuple[WorkspaceConfig, ...]
        Workspaces declared in addition to the default one.
    """

    port: int = 8765
    db_path: Path = _xdg("XDG_DATA_HOME", ".local/share") / "timetracker" / "timetracker.sqlite3"
    sound_file: Path = Path("/usr/share/sounds/freedesktop/stereo/complete.oga")
    timezone: str = "America/Los_Angeles"
    alert_popups: bool = False
    backup_dir: Path | None = None
    backup_keep: int = 14
    workspaces: tuple[WorkspaceConfig, ...] = ()

    def all_workspaces(self) -> tuple[WorkspaceConfig, ...]:
        """Return every workspace, the default one first.

        The default workspace uses ``db_path``, the built-in target and has
        the idle nudge on.
        """
        default = WorkspaceConfig(name=DEFAULT_WORKSPACE, db_path=self.db_path, idle_nudge=True)
        return (default, *self.workspaces)

    def workspace(self, name: str) -> WorkspaceConfig:
        """Return the workspace called ``name``.

        Raises
        ------
        LookupError
            If no such workspace is declared; the message lists the known names.
        """
        known = {w.name: w for w in self.all_workspaces()}
        if name not in known:
            raise LookupError(f"unknown workspace {name!r} (known: {', '.join(known)})")
        return known[name]


def _workspace(name: str, raw: object, db_dir: Path, source: Path) -> WorkspaceConfig:
    """Build one declared workspace from its TOML table."""
    if not _WORKSPACE_NAME.fullmatch(name) or name == DEFAULT_WORKSPACE:
        raise ValueError(
            f"bad workspace name {name!r} in {source}: use lower-case letters, digits and "
            f"hyphens, starting with a letter; {DEFAULT_WORKSPACE!r} is the built-in default"
        )
    if not isinstance(raw, dict):
        raise ValueError(f"workspace {name!r} in {source} must be a table")
    unknown = set(raw) - _WORKSPACE_KEYS
    if unknown:
        raise ValueError(f"unknown keys in workspace {name!r} in {source}: {sorted(unknown)}")
    target = raw.get("target_hours")
    if target is not None and not 0 < target <= 24:
        raise ValueError(f"workspace {name!r} in {source}: target_hours must be in (0, 24]")
    return WorkspaceConfig(
        name=name,
        db_path=Path(raw["db_path"]).expanduser() if "db_path" in raw else db_dir / f"{name}.sqlite3",
        target_hours=target,
        idle_nudge=bool(raw.get("idle_nudge", False)),
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read the configuration file.

    Parameters
    ----------
    path : Path
        TOML file with any of the ``Config`` fields as top-level keys. Extra
        workspaces are tables ``[workspaces.<name>]`` with optional keys
        ``db_path`` (default: ``<name>.sqlite3`` beside the main database),
        ``target_hours`` and ``idle_nudge`` (default false).

    Returns
    -------
    Config
        Defaults overridden by the file's values; pure defaults if the file
        does not exist.

    Raises
    ------
    ValueError
        If the file contains a key that is not a ``Config`` field, or a
        workspace with a bad name, unknown key or out-of-range target.
    """
    if not path.is_file():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown keys in {path}: {sorted(unknown)}")
    declared = raw.pop("workspaces", {})
    if not isinstance(declared, dict):
        raise ValueError(f"'workspaces' in {path} must be a table of [workspaces.<name>] tables")
    converted = {
        key: Path(value).expanduser() if key in ("db_path", "sound_file", "backup_dir") else value
        for key, value in raw.items()
    }
    config = replace(Config(), **converted)
    workspaces = tuple(
        _workspace(name, table, config.db_path.parent, path) for name, table in declared.items()
    )
    return replace(config, workspaces=workspaces)
