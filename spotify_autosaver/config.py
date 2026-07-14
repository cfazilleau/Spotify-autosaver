"""Global configuration for Spotify Autosaver.

Everything is read from a single JSON settings file (see ``settings.py`` and
``settings.example.json``). This module defines the global settings shared by
every account; per-account entries live in the same file.
"""

from __future__ import annotations

from dataclasses import dataclass

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
DEFAULT_TRACK_COUNT = 100
DEFAULT_INTERVAL_SECONDS = 3600


class ConfigError(RuntimeError):
    """Raised when the settings file is missing or invalid."""


def _as_int(value: object, default: int, field: str) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field!r} must be an integer, got {value!r}") from exc


@dataclass
class Config:
    """Global settings shared by every account.

    Also the fallback defaults for per-account fields that an entry omits.
    """

    # Spotify app client id. No client secret is needed: accounts authorize via
    # the PKCE web app, and tokens refresh with the client id alone. (The
    # redirect URI is the web app's own URL — it isn't needed here.)
    client_id: str

    # Defaults applied to accounts that don't override them.
    track_count: int
    playlist_name: str
    playlist_public: bool
    playlist_description: str

    # How the continuous loop behaves.
    interval_seconds: int

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        """Build the global config from the settings file's top-level keys."""

        client_id = str(data.get("client_id") or "").strip()
        if not client_id:
            raise ConfigError(
                "Settings file is missing 'client_id'. See settings.example.json."
            )

        track_count = _as_int(data.get("track_count"), DEFAULT_TRACK_COUNT, "track_count")
        if track_count < 1:
            raise ConfigError("'track_count' must be a positive integer")

        return cls(
            client_id=client_id,
            track_count=track_count,
            playlist_name=str(data.get("playlist_name") or DEFAULT_PLAYLIST_NAME).strip(),
            playlist_public=bool(data.get("playlist_public", False)),
            playlist_description=str(
                data.get("playlist_description") or DEFAULT_PLAYLIST_DESCRIPTION
            ).strip(),
            interval_seconds=_as_int(
                data.get("interval_seconds"), DEFAULT_INTERVAL_SECONDS, "interval_seconds"
            ),
        )
