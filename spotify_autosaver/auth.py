"""Spotify authentication helpers.

Two authentication modes are supported:

* **Interactive** — a one-time browser login that caches a refresh token to a
  local file (``AUTOSAVER_CACHE_PATH``). Best for running on your own machine.
* **Headless** — a stored refresh token supplied per user (via the users file
  or ``SPOTIFY_REFRESH_TOKEN``). Best for servers, containers, and CI where no
  browser is available, and for syncing several accounts at once.
"""

from __future__ import annotations

import spotipy
from spotipy.cache_handler import CacheFileHandler, MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from .config import SCOPE, Config


def build_auth_manager(
    config: Config, refresh_token: str | None = None, *, open_browser: bool = True
) -> SpotifyOAuth:
    """Create a :class:`SpotifyOAuth` manager.

    When ``refresh_token`` is provided the token cache is seeded with it (no
    interactive login is ever needed); otherwise spotipy manages a local cache
    file and prompts for an interactive login on first use.
    """

    if refresh_token:
        # Seed the token cache with the stored refresh token. ``expires_at`` of
        # zero forces spotipy to refresh immediately on first use.
        cache_handler = MemoryCacheHandler(
            token_info={
                "access_token": "",
                "refresh_token": refresh_token,
                "expires_at": 0,
                "scope": SCOPE,
                "token_type": "Bearer",
            }
        )
    else:
        cache_handler = CacheFileHandler(cache_path=config.cache_path)

    return SpotifyOAuth(
        client_id=config.client_id,
        client_secret=config.client_secret,
        redirect_uri=config.redirect_uri,
        scope=SCOPE,
        cache_handler=cache_handler,
        # Always show the consent screen on interactive login so re-auth after a
        # scope change actually re-grants the new scopes (Spotify otherwise
        # silently reuses a prior, possibly narrower, grant).
        show_dialog=True,
        open_browser=open_browser,
    )


def get_client(
    config: Config, refresh_token: str | None = None, *, open_browser: bool = True
) -> spotipy.Spotify:
    """Return an authenticated :class:`spotipy.Spotify` client.

    Pass ``refresh_token`` to authenticate a specific account headlessly; omit
    it to fall back to the interactive/cached login.
    """

    return spotipy.Spotify(
        auth_manager=build_auth_manager(
            config, refresh_token, open_browser=open_browser
        )
    )
