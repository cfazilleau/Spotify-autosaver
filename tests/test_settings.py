"""Tests for loading global config and accounts from the settings file."""

from __future__ import annotations

import json

import pytest

from spotify_autosaver.config import ConfigError
from spotify_autosaver.settings import load_settings


def write_settings(tmp_path, data) -> str:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_globals_and_defaults(tmp_path):
    path = write_settings(
        tmp_path,
        {
            "client_id": "abc",
            "interval_seconds": 10,
            "users": [{"name": "me", "refresh_token": "tok"}],
        },
    )
    config, users = load_settings(path)

    assert config.client_id == "abc"
    assert config.interval_seconds == 10
    assert config.track_count == 100  # default
    assert config.playlist_name == "Liked Songs (Latest 100)"  # default
    assert len(users) == 1 and users[0].name == "me"


def test_per_account_overrides_and_inheritance(tmp_path):
    path = write_settings(
        tmp_path,
        {
            "client_id": "abc",
            "track_count": 100,
            "playlist_name": "Global",
            "users": [
                {"name": "me", "refresh_token": "t1"},
                {"name": "alex", "refresh_token": "t2", "track_count": 50,
                 "playlist_name": "Alex 50", "playlist_public": True},
            ],
        },
    )
    _, users = load_settings(path)

    assert users[0].track_count == 100 and users[0].playlist_name == "Global"
    assert users[1].track_count == 50 and users[1].playlist_name == "Alex 50"
    assert users[1].playlist_public is True


def test_playlist_id_not_inherited_from_global(tmp_path):
    # A global playlist_id key would be account-specific; it must not leak in.
    path = write_settings(
        tmp_path,
        {"client_id": "abc", "playlist_id": "global", "users": [{"refresh_token": "t"}]},
    )
    _, users = load_settings(path)
    assert users[0].playlist_id is None


def test_missing_client_id_errors(tmp_path):
    path = write_settings(tmp_path, {"users": [{"refresh_token": "t"}]})
    with pytest.raises(ConfigError, match="client_id"):
        load_settings(path)


def test_missing_refresh_token_errors(tmp_path):
    path = write_settings(tmp_path, {"client_id": "abc", "users": [{"name": "x"}]})
    with pytest.raises(ConfigError, match="refresh_token"):
        load_settings(path)


def test_no_users_errors(tmp_path):
    path = write_settings(tmp_path, {"client_id": "abc", "users": []})
    with pytest.raises(ConfigError, match="no accounts"):
        load_settings(path)


def test_missing_file_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_settings(str(tmp_path / "nope.json"))


def test_invalid_json_errors(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_settings(str(path))
