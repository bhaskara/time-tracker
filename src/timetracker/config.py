"""Server configuration, optionally read from a TOML file."""

import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path


def _xdg(variable: str, fallback: str) -> Path:
    """Resolve an XDG base directory."""
    return Path(os.environ.get(variable) or Path.home() / fallback)


DEFAULT_CONFIG_PATH = _xdg("XDG_CONFIG_HOME", ".config") / "timetracker" / "config.toml"


@dataclass(frozen=True)
class Config:
    """Server settings.

    Attributes
    ----------
    port : int
        TCP port on 127.0.0.1.
    db_path : Path
        SQLite database file.
    sound_file : Path
        Chime played with notifications.
    timezone : str
        IANA zone in which the 2 AM day boundary is evaluated.
    alert_popups : bool
        Whether time's-up, overrun and break-over alerts show a desktop
        pop-up in addition to the chime.
    """

    port: int = 8765
    db_path: Path = _xdg("XDG_DATA_HOME", ".local/share") / "timetracker" / "timetracker.sqlite3"
    sound_file: Path = Path("/usr/share/sounds/freedesktop/stereo/complete.oga")
    timezone: str = "America/Los_Angeles"
    alert_popups: bool = False


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read the configuration file.

    Parameters
    ----------
    path : Path
        TOML file with any of the ``Config`` fields as top-level keys.

    Returns
    -------
    Config
        Defaults overridden by the file's values; pure defaults if the file
        does not exist.

    Raises
    ------
    ValueError
        If the file contains a key that is not a ``Config`` field.
    """
    if not path.is_file():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown keys in {path}: {sorted(unknown)}")
    converted = {
        key: Path(value).expanduser() if key in ("db_path", "sound_file") else value
        for key, value in raw.items()
    }
    return replace(Config(), **converted)
