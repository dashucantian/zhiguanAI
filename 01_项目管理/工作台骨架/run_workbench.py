from __future__ import annotations

import argparse
import sys

from workbench.client import BasicAuthClient, check_health, format_log_line
from workbench.config import ConfigError, load_config


def _load_config():
    try:
        return load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return None


def cmd_health(args) -> int:
    config = _load_config()
    if config is None:
        return 4

    client = BasicAuthClient(config)
    result = check_health(client, auth=not args.no_auth)
    action = "health-noauth" if args.no_auth else "health"
    print(format_log_line(config, action, result.status, result.elapsed_ms, result.version))

    if result.ok:
        print(f"version={result.version}")
        return 0
    if result.status == 401:
        print("unauthorized", file=sys.stderr)
        return 2
    if result.status is None:
        print(f"connection error: {result.error}", file=sys.stderr)
        return 3
    print(f"http error: {result.status} {result.error or ''}".rstrip(), file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only workbench skeleton for the OpenCode serve API."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    health = sub.add_parser("health", help="GET /global/health (read-only)")
    health.add_argument(
        "--no-auth",
        action="store_true",
        help="send the request without Basic auth (expected 401)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "health":
        return cmd_health(args)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
