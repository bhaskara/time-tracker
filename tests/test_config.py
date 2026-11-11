"""Tests for configuration loading."""

from pathlib import Path

import pytest

from timetracker.config import Config, load_config


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
