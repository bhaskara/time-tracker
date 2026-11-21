"""Tests for configuration loading."""

from pathlib import Path

import pytest

from timetracker.config import Config, WorkspaceConfig, load_config


def test_missing_file_gives_defaults(tmp_path):
    """No file means default settings."""
    assert load_config(tmp_path / "none.toml") == Config()


def test_file_overrides_defaults(tmp_path):
    """Keys in the file override defaults; paths are converted."""
    path = tmp_path / "config.toml"
    path.write_text('port = 9000\ndb_path = "/tmp/x.sqlite3"\n')
    config = load_config(path)
    assert (config.port, config.db_path) == (9000, Path("/tmp/x.sqlite3"))
    assert config.timezone == Config().timezone


def test_unknown_key_rejected(tmp_path):
    """A misspelled key is an error rather than being ignored."""
    path = tmp_path / "config.toml"
    path.write_text("prot = 9000\n")
    with pytest.raises(ValueError, match="unknown keys"):
        load_config(path)


def test_workspaces_declared_as_tables(tmp_path):
    """Extra workspaces get a database beside the main one unless they name their own."""
    path = tmp_path / "config.toml"
    path.write_text(
        'db_path = "/data/tt.sqlite3"\n'
        "[workspaces.personal]\n"
        "[workspaces.side-project]\n"
        'db_path = "/elsewhere/side.sqlite3"\ntarget_hours = 2\nidle_nudge = true\n'
    )
    config = load_config(path)
    assert config.all_workspaces() == (
        WorkspaceConfig("work", Path("/data/tt.sqlite3"), idle_nudge=True),
        WorkspaceConfig("personal", Path("/data/personal.sqlite3")),
        WorkspaceConfig("side-project", Path("/elsewhere/side.sqlite3"), 2, True),
    )
    assert config.workspace("personal").name == "personal"
    with pytest.raises(LookupError, match="known: work, personal, side-project"):
        config.workspace("nope")


@pytest.mark.parametrize(
    "text",
    [
        "[workspaces.work]\n",
        "[workspaces.Bad_Name]\n",
        "[workspaces.personal]\ncolour = 1\n",
        "[workspaces.personal]\ntarget_hours = 0\n",
        "workspaces = 3\n",
    ],
)
def test_bad_workspace_declarations_rejected(tmp_path, text):
    """The default name, odd names, unknown keys and bad targets are errors."""
    path = tmp_path / "config.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_config(path)
