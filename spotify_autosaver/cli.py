"""Command-line interface for Spotify Autosaver."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__
from .auth import get_client
from .autosaver import resolve_playlist_id, sync_if_changed, sync_once
from .config import SCOPE, Config, ConfigError
from .users import UserConfig, load_users

log = logging.getLogger("spotify_autosaver")


def _verify_scopes(client, name: str) -> None:
    """Log the token's actual granted scopes and warn about any that are missing.

    Turns a later opaque 403 into an explicit, up-front message naming the
    missing scope(s).
    """

    try:
        auth = client.auth_manager
        token = auth.validate_token(auth.cache_handler.get_cached_token())
        granted = set((token or {}).get("scope", "").split())
    except Exception:  # noqa: BLE001 — diagnostics must never break startup.
        log.debug("Could not read granted scopes for account %r.", name, exc_info=True)
        return

    if not granted:
        return  # interactive login not completed yet; nothing to check.

    missing = set(SCOPE.split()) - granted
    if missing:
        log.error(
            "Account %r is missing OAuth scope(s): %s. Re-authorize it with the "
            "PKCE web app and update its token in the users file.",
            name,
            " ".join(sorted(missing)),
        )
    else:
        log.info("Account %r authorized with scopes: %s", name, " ".join(sorted(granted)))


def _client_for(config: Config, user: UserConfig):
    """Build a Spotify client for one account."""

    client = get_client(config, user.refresh_token)
    _verify_scopes(client, user.name)
    return client


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_sync(config: Config) -> int:
    """Run a single sync for every account and exit."""

    users = load_users(config)
    log.info("Syncing %d account(s).", len(users))
    failures = 0
    for user in users:
        try:
            client = _client_for(config, user)
            sync_once(client, user)
        except Exception:  # noqa: BLE001 — one bad account shouldn't stop the rest.
            log.exception("Sync failed for account %r.", user.name)
            failures += 1
    return 1 if failures else 0


def cmd_run(config: Config) -> int:
    """Run forever, polling every ``interval_seconds`` and syncing on change.

    Each account is polled independently and keeps its own resolved playlist and
    change-detection signature, so short intervals stay cheap even with several
    accounts.
    """

    users = load_users(config)
    log.info(
        "Starting autosaver loop: %d account(s), polling every %d second(s).",
        len(users),
        config.interval_seconds,
    )

    clients = {user.name: _client_for(config, user) for user in users}
    # Per-account state: resolved playlist id and last library signature.
    playlist_ids: dict[str, str | None] = {user.name: None for user in users}
    signatures: dict[str, object] = {user.name: None for user in users}

    while True:
        for user in users:
            try:
                if playlist_ids[user.name] is None:
                    playlist_ids[user.name] = resolve_playlist_id(
                        clients[user.name], user
                    )
                signatures[user.name], _ = sync_if_changed(
                    clients[user.name],
                    user,
                    playlist_ids[user.name],
                    signatures[user.name],
                )
            except Exception:  # noqa: BLE001 — keep the loop alive across failures.
                log.exception("Poll failed for account %r; will retry.", user.name)
                # Force a fresh resolve + full sync for this account next time.
                playlist_ids[user.name] = None
                signatures[user.name] = None
        time.sleep(config.interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spotify-autosaver",
        description=(
            "Maintain a Spotify playlist that mirrors your most recently liked "
            "songs."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="Run a single sync for every account and exit.")
    sub.add_parser("run", help="Run continuously, syncing each account on change.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    try:
        config = Config.from_env()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    handlers = {"sync": cmd_sync, "run": cmd_run}
    return handlers[args.command](config)


if __name__ == "__main__":
    sys.exit(main())
