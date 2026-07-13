"""Loading the set of accounts to sync.

Each account ("user") is described by a refresh token plus optional per-user
overrides of the playlist settings. Users can be listed in a mounted JSON file
(``AUTOSAVER_USERS_FILE``, default ``users.json``) so friends' tokens can be
added over time without touching the code or environment.

The JSON may be either an object with a ``users`` array or a bare array::

    {
      "users": [
        { "name": "clement", "refresh_token": "AQ..." },
        { "name": "alex", "refresh_token": "AQ...", "playlist_name": "Alex latest 100" }
      ]
    }

When no users file is present the tool falls back to a single account taken from
the environment (``SPOTIFY_REFRESH_TOKEN``, or the interactive/cached login),
preserving the original single-user behaviour.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .config import Config, ConfigError


@dataclass
class UserConfig:
    """One account to sync, with resolved (defaults-applied) playlist settings.

    The attribute names mirror :class:`~spotify_autosaver.config.Config` so the
    same sync functions accept either object.
    """

    name: str
    refresh_token: str | None
    track_count: int
    playlist_id: str | None
    playlist_name: str
    playlist_public: bool
    playlist_description: str


def _user_from_entry(entry: dict, index: int, config: Config, source: str) -> UserConfig:
    if not isinstance(entry, dict):
        raise ConfigError(f"{source}: user #{index + 1} must be a JSON object")

    token = (entry.get("refresh_token") or "").strip()
    if not token:
        raise ConfigError(
            f"{source}: user #{index + 1} is missing a non-empty 'refresh_token'"
        )

    try:
        track_count = int(entry.get("track_count", config.track_count))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"{source}: user #{index + 1} has an invalid 'track_count'"
        ) from exc
    if track_count < 1:
        raise ConfigError(
            f"{source}: user #{index + 1} 'track_count' must be a positive integer"
        )

    return UserConfig(
        name=str(entry.get("name") or f"user{index + 1}"),
        refresh_token=token,
        track_count=track_count,
        # A playlist id is account-specific, so it is never inherited from the
        # global default — only an explicit per-user value is used.
        playlist_id=(entry.get("playlist_id") or None),
        playlist_name=str(entry.get("playlist_name") or config.playlist_name),
        playlist_public=bool(entry.get("playlist_public", config.playlist_public)),
        playlist_description=str(
            entry.get("playlist_description") or config.playlist_description
        ),
    )


def _load_from_file(path: str, config: Config) -> list[UserConfig]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    if isinstance(data, dict):
        entries = data.get("users", [])
    elif isinstance(data, list):
        entries = data
    else:
        raise ConfigError(
            f"{path} must be a JSON array or an object with a 'users' array"
        )

    if not entries:
        raise ConfigError(f"{path} contains no users")

    return [_user_from_entry(entry, i, config, path) for i, entry in enumerate(entries)]


def _single_user_from_env(config: Config) -> UserConfig:
    """Fallback single account from the environment / interactive login."""

    return UserConfig(
        name="default",
        refresh_token=config.refresh_token,
        track_count=config.track_count,
        playlist_id=config.playlist_id,
        playlist_name=config.playlist_name,
        playlist_public=config.playlist_public,
        playlist_description=config.playlist_description,
    )


def load_users(config: Config) -> list[UserConfig]:
    """Return the accounts to sync.

    Uses the users file when it exists, otherwise a single environment-based
    account.
    """

    if config.users_file and os.path.exists(config.users_file):
        return _load_from_file(config.users_file, config)
    return [_single_user_from_env(config)]
