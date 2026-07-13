"""Core sync logic: mirror the most recent liked songs into a playlist."""

from __future__ import annotations

import logging

import spotipy

from .config import Config

log = logging.getLogger(__name__)

# Spotify caps most track-related requests at 100 items per call.
_MAX_PAGE = 50
_MAX_ITEMS_PER_REQUEST = 100


def fetch_recent_liked_uris(client: spotipy.Spotify, limit: int) -> list[str]:
    """Return the URIs of the ``limit`` most recently liked (saved) tracks.

    Spotify's *saved tracks* endpoint returns items ordered most-recently-added
    first, so the first ``limit`` items are exactly what we want. Local files and
    unavailable tracks (which have no URI) are skipped.
    """

    uris: list[str] = []
    results = client.current_user_saved_tracks(limit=min(_MAX_PAGE, limit))

    while results is not None:
        for item in results.get("items", []):
            track = item.get("track") or {}
            uri = track.get("uri")
            # Skip local files — they cannot be added to a playlist by URI.
            if uri and not track.get("is_local"):
                uris.append(uri)
            if len(uris) >= limit:
                return uris[:limit]

        if results.get("next"):
            results = client.next(results)
        else:
            break

    return uris[:limit]


def find_playlist(client: spotipy.Spotify, name: str, owner_id: str) -> str | None:
    """Return the id of the current user's playlist named ``name``, if any."""

    playlists = client.current_user_playlists(limit=_MAX_PAGE)
    while playlists is not None:
        for playlist in playlists.get("items", []):
            owner = (playlist.get("owner") or {}).get("id")
            if playlist.get("name") == name and owner == owner_id:
                return playlist["id"]
        if playlists.get("next"):
            playlists = client.next(playlists)
        else:
            break
    return None


def resolve_playlist_id(client: spotipy.Spotify, config: Config) -> str:
    """Return the target playlist id, creating the playlist if necessary."""

    if config.playlist_id:
        return config.playlist_id

    user_id = client.me()["id"]
    existing = find_playlist(client, config.playlist_name, user_id)
    if existing:
        log.info("Using existing playlist %r (%s)", config.playlist_name, existing)
        return existing

    created = client.user_playlist_create(
        user=user_id,
        name=config.playlist_name,
        public=config.playlist_public,
        description=config.playlist_description,
    )
    log.info("Created playlist %r (%s)", config.playlist_name, created["id"])
    return created["id"]


def replace_playlist_items(
    client: spotipy.Spotify, playlist_id: str, uris: list[str]
) -> None:
    """Replace the playlist's contents with ``uris`` (handles >100 items)."""

    first_chunk = uris[:_MAX_ITEMS_PER_REQUEST]
    client.playlist_replace_items(playlist_id, first_chunk)

    for start in range(_MAX_ITEMS_PER_REQUEST, len(uris), _MAX_ITEMS_PER_REQUEST):
        client.playlist_add_items(
            playlist_id, uris[start : start + _MAX_ITEMS_PER_REQUEST]
        )


def sync_once(client: spotipy.Spotify, config: Config) -> int:
    """Perform a single sync. Returns the number of tracks written."""

    uris = fetch_recent_liked_uris(client, config.track_count)
    if not uris:
        log.warning("No liked songs found — nothing to sync.")
        return 0

    playlist_id = resolve_playlist_id(client, config)
    replace_playlist_items(client, playlist_id, uris)
    log.info("Synced %d track(s) into playlist %s", len(uris), playlist_id)
    return len(uris)


# A cheap fingerprint of the Liked Songs library: (total_count, newest_uri).
# Comparing it between polls detects any relevant change with a single API call:
#   - a new like        -> total increases and the newest track changes
#   - unliking the top   -> the newest track changes
#   - unliking any other -> total decreases (newest may be unchanged)
LibrarySignature = tuple[int | None, str | None]


def fetch_liked_signature(client: spotipy.Spotify) -> LibrarySignature:
    """Return a lightweight ``(total, newest_uri)`` fingerprint in one API call."""

    results = client.current_user_saved_tracks(limit=1)
    total = results.get("total")
    items = results.get("items") or []
    newest = None
    if items:
        track = items[0].get("track") or {}
        newest = track.get("uri")
    return (total, newest)


def sync_if_changed(
    client: spotipy.Spotify,
    config: Config,
    playlist_id: str,
    last_signature: LibrarySignature | None,
) -> tuple[LibrarySignature, int]:
    """Sync only when the library fingerprint changed since ``last_signature``.

    Returns the current signature and the number of tracks written (``0`` when
    nothing changed, so no full fetch or playlist write happens).
    """

    signature = fetch_liked_signature(client)
    if signature == last_signature:
        log.debug("No change in liked songs; skipping sync.")
        return signature, 0

    uris = fetch_recent_liked_uris(client, config.track_count)
    replace_playlist_items(client, playlist_id, uris)
    log.info(
        "Change detected (%s) → synced %d track(s) into playlist %s",
        signature,
        len(uris),
        playlist_id,
    )
    return signature, len(uris)
