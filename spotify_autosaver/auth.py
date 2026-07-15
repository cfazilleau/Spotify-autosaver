"""Spotify authentication.

Accounts authorize once through the PKCE web app (see ``docs/index.html``) and
their refresh token is stored in the users file. At runtime we refresh that
token using the Authorization Code with PKCE flow, which needs only the client
id — no client secret is ever required or stored on the server.
"""

from __future__ import annotations

import spotipy
from spotipy.cache_handler import MemoryCacheHandler
from spotipy.oauth2 import SpotifyPKCE

from .config import SCOPE, Config

# SpotifyPKCE requires a redirect_uri, but it is only used to build the
# authorization URL during interactive login — never on the refresh path, which
# is all we do here. The real redirect URI lives in the web app. This placeholder
# just satisfies the constructor.
_UNUSED_REDIRECT_URI = "http://127.0.0.1/callback"


def get_client(config: Config, refresh_token: str) -> spotipy.Spotify:
    """Return an authenticated client for the account owning ``refresh_token``."""

    # Seed an in-memory cache with the stored refresh token. expires_at=0 forces
    # spotipy to refresh immediately on first use, so no interactive login runs.
    cache_handler = MemoryCacheHandler(
        token_info={
            "access_token": "",
            "refresh_token": refresh_token,
            "expires_at": 0,
            "scope": SCOPE,
            "token_type": "Bearer",
        }
    )
    auth_manager = SpotifyPKCE(
        client_id=config.client_id,
        redirect_uri=_UNUSED_REDIRECT_URI,
        scope=SCOPE,
        cache_handler=cache_handler,
        open_browser=False,
    )
    return spotipy.Spotify(auth_manager=auth_manager)
