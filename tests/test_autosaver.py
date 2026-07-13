"""Tests for the core sync logic using a fake Spotify client."""

from __future__ import annotations

from spotify_autosaver.autosaver import (
    fetch_liked_signature,
    fetch_recent_liked_uris,
    find_playlist,
    replace_playlist_items,
    resolve_playlist_id,
    sync_if_changed,
    sync_once,
)
from spotify_autosaver.config import Config


def make_config(**overrides) -> Config:
    base = dict(
        client_id="id",
        client_secret="secret",
        redirect_uri="http://127.0.0.1:8888/callback",
        refresh_token=None,
        cache_path=".cache",
        track_count=100,
        playlist_id=None,
        playlist_name="Liked Songs (Latest 100)",
        playlist_public=False,
        playlist_description="desc",
        interval_seconds=3600,
    )
    base.update(overrides)
    return Config(**base)


def _track(uri: str, is_local: bool = False) -> dict:
    return {"track": {"uri": uri, "is_local": is_local}}


class FakeSpotify:
    """Minimal stand-in for spotipy.Spotify, backed by in-memory pages."""

    def __init__(self, saved_pages=None, playlist_pages=None, user_id="me"):
        self._saved_pages = saved_pages or [{"items": [], "next": None}]
        self._playlist_pages = playlist_pages or [{"items": [], "next": None}]
        self._user_id = user_id
        # Recorded interactions for assertions.
        self.replaced = []
        self.added = []
        self.created = []

    # --- paging -----------------------------------------------------------
    def current_user_saved_tracks(self, limit=50):
        self._saved_cursor = 0
        return self._saved_pages[0]

    def current_user_playlists(self, limit=50):
        self._playlist_cursor = 0
        return self._playlist_pages[0]

    def next(self, page):
        # ``page["next"]`` holds the index of the following page (or None).
        idx = page["next"]
        if idx is None:
            return None
        # Return the next page from whichever collection this page belongs to.
        if any(page is p for p in self._saved_pages):
            return self._saved_pages[idx]
        return self._playlist_pages[idx]

    # --- account ----------------------------------------------------------
    def me(self):
        return {"id": self._user_id}

    # --- playlist mutations ----------------------------------------------
    def user_playlist_create(self, user, name, public, description):
        pid = "created123"
        self.created.append({"user": user, "name": name, "public": public})
        return {"id": pid}

    def playlist_replace_items(self, playlist_id, uris):
        self.replaced.append((playlist_id, list(uris)))

    def playlist_add_items(self, playlist_id, uris):
        self.added.append((playlist_id, list(uris)))


def _linked_pages(pages):
    """Wire up ``next`` indices for a list of page dicts."""
    for i, page in enumerate(pages):
        page["next"] = i + 1 if i + 1 < len(pages) else None
    return pages


def test_fetch_recent_liked_respects_limit_and_order():
    pages = _linked_pages(
        [
            {"items": [_track(f"spotify:track:{i}") for i in range(50)]},
            {"items": [_track(f"spotify:track:{i}") for i in range(50, 120)]},
        ]
    )
    sp = FakeSpotify(saved_pages=pages)
    uris = fetch_recent_liked_uris(sp, limit=100)
    assert len(uris) == 100
    assert uris[0] == "spotify:track:0"
    assert uris[-1] == "spotify:track:99"


def test_fetch_recent_liked_skips_local_and_missing_uris():
    pages = _linked_pages(
        [
            {
                "items": [
                    _track("spotify:track:a"),
                    _track("spotify:local:x", is_local=True),
                    {"track": None},
                    _track("spotify:track:b"),
                ]
            }
        ]
    )
    sp = FakeSpotify(saved_pages=pages)
    uris = fetch_recent_liked_uris(sp, limit=100)
    assert uris == ["spotify:track:a", "spotify:track:b"]


def test_find_playlist_matches_name_and_owner():
    pages = _linked_pages(
        [
            {
                "items": [
                    {"id": "p1", "name": "Other", "owner": {"id": "me"}},
                    {"id": "p2", "name": "Target", "owner": {"id": "someone"}},
                    {"id": "p3", "name": "Target", "owner": {"id": "me"}},
                ]
            }
        ]
    )
    sp = FakeSpotify(playlist_pages=pages)
    assert find_playlist(sp, "Target", "me") == "p3"
    assert find_playlist(sp, "Missing", "me") is None


def test_resolve_playlist_id_prefers_explicit_id():
    sp = FakeSpotify()
    config = make_config(playlist_id="explicit")
    assert resolve_playlist_id(sp, config) == "explicit"


def test_resolve_playlist_id_creates_when_absent():
    sp = FakeSpotify(playlist_pages=_linked_pages([{"items": []}]))
    config = make_config()
    assert resolve_playlist_id(sp, config) == "created123"
    assert sp.created and sp.created[0]["name"] == config.playlist_name


def test_replace_playlist_items_chunks_beyond_100():
    sp = FakeSpotify()
    uris = [f"spotify:track:{i}" for i in range(230)]
    replace_playlist_items(sp, "pid", uris)
    assert sp.replaced == [("pid", uris[:100])]
    assert sp.added == [("pid", uris[100:200]), ("pid", uris[200:230])]


def test_sync_once_end_to_end():
    saved = _linked_pages(
        [{"items": [_track(f"spotify:track:{i}") for i in range(10)]}]
    )
    sp = FakeSpotify(
        saved_pages=saved, playlist_pages=_linked_pages([{"items": []}])
    )
    config = make_config(track_count=10)
    written = sync_once(sp, config)
    assert written == 10
    assert sp.replaced[0][0] == "created123"
    assert len(sp.replaced[0][1]) == 10


def test_sync_once_no_liked_songs_is_noop():
    sp = FakeSpotify(saved_pages=_linked_pages([{"items": []}]))
    config = make_config()
    assert sync_once(sp, config) == 0
    assert sp.replaced == []


def test_fetch_liked_signature_reports_total_and_newest():
    pages = _linked_pages(
        [{"total": 42, "items": [_track("spotify:track:newest")]}]
    )
    sp = FakeSpotify(saved_pages=pages)
    assert fetch_liked_signature(sp) == (42, "spotify:track:newest")


def test_fetch_liked_signature_handles_empty_library():
    pages = _linked_pages([{"total": 0, "items": []}])
    sp = FakeSpotify(saved_pages=pages)
    assert fetch_liked_signature(sp) == (0, None)


def test_sync_if_changed_skips_when_signature_unchanged():
    pages = _linked_pages(
        [{"total": 5, "items": [_track(f"spotify:track:{i}") for i in range(5)]}]
    )
    sp = FakeSpotify(saved_pages=pages)
    config = make_config(track_count=5)

    signature, written = sync_if_changed(sp, config, "pid", last_signature=None)
    assert written == 5
    assert signature == (5, "spotify:track:0")
    assert sp.replaced[0][0] == "pid"

    # Same signature on the next poll -> no fetch, no write.
    signature2, written2 = sync_if_changed(sp, config, "pid", last_signature=signature)
    assert written2 == 0
    assert signature2 == signature
    assert len(sp.replaced) == 1  # unchanged: still only the first write
