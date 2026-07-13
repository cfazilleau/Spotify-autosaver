"""Configuration loading for Spotify Autosaver.

All settings are read from environment variables (optionally populated from a
``.env`` file). See ``.env.example`` for the full list and documentation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# OAuth scopes required to read the library, list playlists (to find the target
# by name), and edit playlists. playlist-read-private is needed for the
# GET /me/playlists lookup — without it Spotify returns 403 "Insufficient scope".
SCOPE = (
    "user-library-read "
    "playlist-read-private "
    "playlist-modify-public "
    "playlist-modify-private"
)

DEFAULT_PLAYLIST_NAME = "Liked Songs (Latest 100)"
DEFAULT_PLAYLIST_DESCRIPTION = (
    "Automatically maintained by Spotify Autosaver — mirrors my most recently "
    "liked songs."
)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass
class Config:
    """Runtime configuration for the autosaver."""

    client_id: str
    client_secret: str
    redirect_uri: str

    # Auth: either a stored refresh token (headless / CI) or a cache file that
    # spotipy manages after an interactive login. For multiple accounts, list
    # their tokens in the users file (see ``users_file``) instead.
    refresh_token: str | None
    cache_path: str
    users_file: str

    # What to sync.
    track_count: int
    playlist_id: str | None
    playlist_name: str
    playlist_public: bool
    playlist_description: str

    # How the long-running loop behaves.
    interval_seconds: int

    @classmethod
    def from_env(cls, *, require_secrets: bool = True) -> Config:
        """Build a :class:`Config` from the process environment.

        Loads a ``.env`` file if present. When ``require_secrets`` is true the
        Spotify client credentials must be set, otherwise a :class:`ConfigError`
        is raised.
        """

        load_dotenv()

        client_id = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv(
            "SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
        ).strip()

        if require_secrets:
            missing = [
                name
                for name, value in (
                    ("SPOTIPY_CLIENT_ID", client_id),
                    ("SPOTIPY_CLIENT_SECRET", client_secret),
                )
                if not value
            ]
            if missing:
                raise ConfigError(
                    "Missing required environment variable(s): "
                    + ", ".join(missing)
                    + ". See .env.example for setup instructions."
                )

        track_count = _get_int("AUTOSAVER_TRACK_COUNT", 100)
        if track_count < 1:
            raise ConfigError("AUTOSAVER_TRACK_COUNT must be a positive integer")

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            refresh_token=(os.getenv("SPOTIFY_REFRESH_TOKEN") or "").strip() or None,
            cache_path=os.getenv("AUTOSAVER_CACHE_PATH", ".cache").strip() or ".cache",
            users_file=os.getenv("AUTOSAVER_USERS_FILE", "users.json").strip()
            or "users.json",
            track_count=track_count,
            playlist_id=(os.getenv("AUTOSAVER_PLAYLIST_ID") or "").strip() or None,
            playlist_name=os.getenv(
                "AUTOSAVER_PLAYLIST_NAME", DEFAULT_PLAYLIST_NAME
            ).strip()
            or DEFAULT_PLAYLIST_NAME,
            playlist_public=_get_bool("AUTOSAVER_PLAYLIST_PUBLIC", False),
            playlist_description=os.getenv(
                "AUTOSAVER_PLAYLIST_DESCRIPTION", DEFAULT_PLAYLIST_DESCRIPTION
            ).strip(),
            interval_seconds=_get_int("AUTOSAVER_INTERVAL_SECONDS", 3600),
        )
