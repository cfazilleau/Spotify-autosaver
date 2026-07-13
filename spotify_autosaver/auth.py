"""Spotify authentication helpers.

Two authentication modes are supported:

* **Interactive** — a one-time browser login that caches a refresh token to a
  local file (``AUTOSAVER_CACHE_PATH``). Best for running on your own machine.
* **Headless** — a ``SPOTIFY_REFRESH_TOKEN`` supplied via the environment. Best
  for servers, containers, and CI (e.g. GitHub Actions) where no browser is
  available.
"""

from __future__ import annotations

import spotipy
from spotipy.cache_handler import CacheFileHandler, MemoryCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from .config import SCOPE, Config


def build_auth_manager(config: Config, *, open_browser: bool = True) -> SpotifyOAuth:
    """Create a :class:`SpotifyOAuth` manager for the given configuration."""

    if config.refresh_token:
        # Seed the token cache with the stored refresh token. ``expires_at`` of
        # zero forces spotipy to refresh immediately on first use, so we never
        # need an interactive login.
        cache_handler = MemoryCacheHandler(
            token_info={
                "access_token": "",
                "refresh_token": config.refresh_token,
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
        open_browser=open_browser,
    )


def get_client(config: Config, *, open_browser: bool = True) -> spotipy.Spotify:
    """Return an authenticated :class:`spotipy.Spotify` client."""

    return spotipy.Spotify(auth_manager=build_auth_manager(config, open_browser=open_browser))
