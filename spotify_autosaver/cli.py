"""Command-line interface for Spotify Autosaver."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from . import __version__
from .auth import build_auth_manager, get_client
from .autosaver import sync_once
from .config import Config, ConfigError

log = logging.getLogger("spotify_autosaver")


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_sync(config: Config) -> int:
    """Run a single sync and exit."""

    client = get_client(config, open_browser=not config.refresh_token)
    sync_once(client, config)
    return 0


def cmd_run(config: Config) -> int:
    """Run forever, syncing every ``interval_seconds``."""

    client = get_client(config, open_browser=not config.refresh_token)
    log.info(
        "Starting autosaver loop: %d track(s) every %d second(s).",
        config.track_count,
        config.interval_seconds,
    )
    while True:
        try:
            sync_once(client, config)
        except Exception:  # noqa: BLE001 — keep the loop alive across failures.
            log.exception("Sync failed; will retry after the interval.")
        time.sleep(config.interval_seconds)


def cmd_auth(config: Config) -> int:
    """Interactively authenticate and print a reusable refresh token."""

    auth_manager = build_auth_manager(config, open_browser=True)
    token_info = auth_manager.get_access_token(as_dict=True)
    refresh_token = token_info["refresh_token"]
    print("\nAuthentication successful!\n")
    print("Store this refresh token as the SPOTIFY_REFRESH_TOKEN secret to run")
    print("headlessly (e.g. in Docker or GitHub Actions):\n")
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
