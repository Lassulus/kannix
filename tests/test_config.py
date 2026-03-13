"""Tests for config loading and validation."""

import json
from pathlib import Path

import pytest

from kannix.config import KannixConfig, load_config


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def valid_config(config_dir: Path) -> Path:
    config = {
        "columns": ["Backlog", "In Progress", "Review", "Done"],
        "hooks": {
            "on_create": "tmux new-session -d -s $TICKET_ID",
            "on_move": {
                "Backlog->In Progress": "echo moving",
            },
            "on_delete": "tmux kill-session -t $TICKET_ID",
        },
        "server": {
            "host": "0.0.0.0",
            "port": 8080,
        },
    }
    path = config_dir / "kannix.json"
    path.write_text(json.dumps(config))
    return path


def test_load_valid_config(valid_config: Path):
    config = load_config(valid_config)
    assert isinstance(config, KannixConfig)
    assert config.columns == ["Backlog", "In Progress", "Review", "Done"]
    assert config.hooks.on_create == "tmux new-session -d -s $TICKET_ID"
    assert config.hooks.on_delete == "tmux kill-session -t $TICKET_ID"
    assert config.hooks.on_move == {"Backlog->In Progress": "echo moving"}
    assert config.server.host == "0.0.0.0"
    assert config.server.port == 8080


def test_load_missing_file_raises(config_dir: Path):
    with pytest.raises(FileNotFoundError):
        load_config(config_dir / "nonexistent.json")


def test_load_invalid_json(config_dir: Path):
    path = config_dir / "bad.json"
    path.write_text("not json {{{")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_config(path)


def test_load_missing_required_columns(config_dir: Path):
    path = config_dir / "no_columns.json"
    path.write_text(json.dumps({"hooks": {}, "server": {}}))
    with pytest.raises(ValueError, match="columns"):
        load_config(path)


def test_load_empty_columns_rejected(config_dir: Path):
    path = config_dir / "empty_cols.json"
    path.write_text(json.dumps({"columns": []}))
    with pytest.raises(ValueError, match="columns"):
        load_config(path)


def test_default_server_values(config_dir: Path):
    path = config_dir / "minimal.json"
    path.write_text(json.dumps({"columns": ["Todo", "Done"]}))
    config = load_config(path)
    assert config.server.host == "0.0.0.0"
    assert config.server.port == 8080


def test_default_hooks_are_empty(config_dir: Path):
    path = config_dir / "minimal.json"
    path.write_text(json.dumps({"columns": ["Todo", "Done"]}))
    config = load_config(path)
    assert config.hooks.on_create is None
    assert config.hooks.on_delete is None
    assert config.hooks.on_move == {}


def test_columns_must_be_unique(config_dir: Path):
    path = config_dir / "dupes.json"
    path.write_text(json.dumps({"columns": ["Todo", "Todo"]}))
    with pytest.raises(ValueError, match="unique"):
        load_config(path)
