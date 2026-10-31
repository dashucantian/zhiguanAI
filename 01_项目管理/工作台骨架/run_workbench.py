from __future__ import annotations

import argparse
import json
import sys

from workbench.client import BasicAuthClient, check_health, format_log_line
from workbench.config import ConfigError, load_config
from workbench.lifecycle import check_lifecycle
from workbench.sessions import SessionError, list_sessions


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


def cmd_sessions(args) -> int:
    config = _load_config()
    if config is None:
        return 4

    client = BasicAuthClient(config)
    try:
        result = list_sessions(client)
    except SessionError as exc:
        message = str(exc)
        print(f"session error: {message}", file=sys.stderr)
        if "connection error" in message or "timeout" in message.lower():
            return 3
        if message.startswith("HTTP"):
            return 2
        return 5

    print(format_log_line(config, "session-list", result.status, result.elapsed_ms))
    print(json.dumps(result.sessions, ensure_ascii=False, indent=2))
    return 0


def cmd_lifecycle(args) -> int:
    config = _load_config()
    if config is None:
        return 4

    if args.dry_run:
        print(f"dry-run: would check {config.safe_url} timeout={config.timeout}s")
        return 0

    result = check_lifecycle(config)
    print(
        f"port_before={result.port_before} port_after={result.port_after} "
        f"exit_code={result.exit_code}"
    )
    if result.health_status is not None:
        print(f"health_http={result.health_status} version={result.health_version}")
    if result.error:
        print(f"lifecycle error: {result.error}", file=sys.stderr)
    return result.exit_code


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
    sub.add_parser("sessions", help="GET /session metadata only (read-only)")
    lifecycle = sub.add_parser(
        "lifecycle",
        help="check an existing serve port (never starts or stops the service)",
    )
    lifecycle.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan only; no network calls",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "health":
        return cmd_health(args)
    if args.command == "sessions":
        return cmd_sessions(args)
    if args.command == "lifecycle":
        return cmd_lifecycle(args)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
