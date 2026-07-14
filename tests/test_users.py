"""Tests for loading accounts from the users file / environment."""

from __future__ import annotations

import json

import pytest

from spotify_autosaver.config import Config, ConfigError
from spotify_autosaver.users import load_users


def make_config(tmp_path, **overrides) -> Config:
    base = dict(
        client_id="id",
        redirect_uri="https://example.github.io/app/",
        users_file=str(tmp_path / "users.json"),
        track_count=100,
        playlist_id=None,
        playlist_name="Liked Songs (Latest 100)",
        playlist_public=False,
        playlist_description="desc",
        interval_seconds=3600,
    )
    base.update(overrides)
    return Config(**base)


def write_users(tmp_path, data) -> None:
    (tmp_path / "users.json").write_text(json.dumps(data), encoding="utf-8")


def test_load_users_applies_defaults_and_overrides(tmp_path):
    write_users(
        tmp_path,
        {
            "users": [
                {"name": "me", "refresh_token": "tok-me"},
                {
                    "name": "alex",
                    "refresh_token": "tok-alex",
                    "playlist_name": "Alex 100",
                    "track_count": 50,
                    "playlist_public": True,
                },
            ]
        },
    )
    users = load_users(make_config(tmp_path))

    assert [u.name for u in users] == ["me", "alex"]

    me = users[0]
    assert me.refresh_token == "tok-me"
    assert me.track_count == 100  # default
    assert me.playlist_name == "Liked Songs (Latest 100)"  # default
    assert me.playlist_public is False

    alex = users[1]
    assert alex.refresh_token == "tok-alex"
    assert alex.track_count == 50  # override
    assert alex.playlist_name == "Alex 100"
    assert alex.playlist_public is True


def test_load_users_accepts_bare_array(tmp_path):
    write_users(tmp_path, [{"refresh_token": "tok"}])
    users = load_users(make_config(tmp_path))
    assert len(users) == 1
    assert users[0].name == "user1"  # auto-named
    assert users[0].refresh_token == "tok"


def test_playlist_id_is_not_inherited_from_global_default(tmp_path):
    write_users(tmp_path, [{"refresh_token": "tok"}])
    users = load_users(make_config(tmp_path, playlist_id="global-id"))
    # A playlist id is account-specific; the global default must not leak in.
    assert users[0].playlist_id is None


def test_missing_refresh_token_is_an_error(tmp_path):
    write_users(tmp_path, [{"name": "oops"}])
    with pytest.raises(ConfigError, match="refresh_token"):
        load_users(make_config(tmp_path))


def test_empty_users_file_is_an_error(tmp_path):
    write_users(tmp_path, {"users": []})
    with pytest.raises(ConfigError, match="no users"):
        load_users(make_config(tmp_path))


def test_invalid_json_is_an_error(tmp_path):
    (tmp_path / "users.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_users(make_config(tmp_path))


def test_missing_users_file_is_an_error(tmp_path):
    # users_file points at a path that doesn't exist.
    config = make_config(tmp_path)  # no users.json written
    with pytest.raises(ConfigError, match="not found"):
        load_users(config)
