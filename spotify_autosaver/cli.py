"""Command-line interface for Spotify Autosaver."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__
from .auth import build_auth_manager, get_client
from .autosaver import resolve_playlist_id, sync_if_changed, sync_once
from .config import Config, ConfigError
from .users import UserConfig, load_users

log = logging.getLogger("spotify_autosaver")


def _client_for(config: Config, user: UserConfig):
    """Build a Spotify client for one account."""

    # With a stored token no browser is needed; without one, fall back to the
    # interactive/cached login.
    return get_client(
        config, user.refresh_token, open_browser=user.refresh_token is None
    )


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


def cmd_auth(config: Config) -> int:
    """Interactively authenticate and print a reusable refresh token."""

    auth_manager = build_auth_manager(config, open_browser=True)
    token_info = auth_manager.get_access_token(as_dict=True)
    refresh_token = token_info["refresh_token"]
    print("\nAuthentication successful!\n")
    print("Add this account to your users file (default users.json):\n")
    print(f'  {{ "name": "me", "refresh_token": "{refresh_token}" }}\n')
    print("Or, for a single account, set it in the environment instead:\n")
    print(f"  SPOTIFY_REFRESH_TOKEN={refresh_token}\n")
    return 0


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
    sub.add_parser("sync", help="Run a single sync and exit (ideal for cron / CI).")
    sub.add_parser("run", help="Run continuously, syncing on an interval.")
    sub.add_parser(
        "auth", help="Interactively log in and print a reusable refresh token."
    )
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

    handlers = {"sync": cmd_sync, "run": cmd_run, "auth": cmd_auth}
    return handlers[args.command](config)


if __name__ == "__main__":
    sys.exit(main())
