from __future__ import annotations

import argparse
from dataclasses import replace
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workbench.client import BasicAuthClient, check_health, format_log_line
from workbench.config import ConfigError, load_config
from workbench.exit_codes import (
    EXIT_CONFIG,
    EXIT_CONNECTION,
    EXIT_HTTP,
    EXIT_OK,
    EXIT_PROTOCOL,
)
from workbench.lifecycle import check_lifecycle
from workbench.sessions import SessionError, list_sessions


def _load_config(args=None):
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return None
    if args is not None and getattr(args, "local_fake", False):
        config = replace(config, level="L0_LOCAL")
    return config


def cmd_health(args) -> int:
    config = _load_config(args)
    if config is None:
        return EXIT_CONFIG

    client = BasicAuthClient(config)
    result = check_health(client, auth=not args.no_auth)
    action = "health-noauth" if args.no_auth else "health"
    if result.version:
        summary = f"version={result.version}"
    elif result.status in (401, 403):
        summary = "unauthorized"
    else:
        summary = result.error or "-"
    print(format_log_line(
        config, action, result.status, result.elapsed_ms,
        version=result.version, summary=summary,
    ))

    if result.ok:
        print(f"version={result.version}")
        return EXIT_OK
    if result.status in (401, 403):
        print("unauthorized", file=sys.stderr)
        return EXIT_HTTP
    if result.status is None:
        print(f"connection error: {result.error}", file=sys.stderr)
        return EXIT_CONNECTION
    print(f"http error: {result.status} {result.error or ''}".rstrip(), file=sys.stderr)
    return EXIT_HTTP


def cmd_sessions(args) -> int:
    config = _load_config(args)
    if config is None:
        return EXIT_CONFIG

    client = BasicAuthClient(config)
    try:
        result = list_sessions(client, show_directory=args.show_directory)
    except SessionError as exc:
        message = str(exc)
        print(f"session error: {message}", file=sys.stderr)
        if "connection error" in message or "timeout" in message.lower():
            return EXIT_CONNECTION
        if message.startswith("HTTP"):
            return EXIT_HTTP
        return EXIT_PROTOCOL

    print(format_log_line(
        config, "session-list", result.status, result.elapsed_ms,
        summary=f"sessions={len(result.sessions)}",
    ))
    print(json.dumps(result.sessions, ensure_ascii=False, indent=2))
    return EXIT_OK


def cmd_lifecycle(args) -> int:
    config = _load_config(args)
    if config is None:
        return EXIT_CONFIG

    result = check_lifecycle(config, dry_run=args.dry_run)
    if result.dry_run:
        print(f"dry-run: no request sent; target={config.safe_url} level={config.level}")
        print("port_before=not-checked port_after=not-checked exit_code=0")
        print(format_log_line(config, "lifecycle-dry-run", None, 0, summary="dry-run=1"))
        return EXIT_OK

    summary = f"port_before={result.port_before} port_after={result.port_after}"
    print(format_log_line(
        config, "lifecycle", result.health_status, result.health_elapsed_ms or 0,
        version=result.health_version, summary=summary,
    ))
    print(
        f"port_before={result.port_before} port_after={result.port_after} "
        f"health={result.health_status} exit_code={result.exit_code}"
    )
    if result.error:
        print(f"lifecycle error: {result.error}", file=sys.stderr)
    return result.exit_code


def _add_local_fake(parser) -> None:
    parser.add_argument(
        "--local-fake",
        action="store_true",
        help="label this run L0_LOCAL (local stub; does not change the target)",
    )


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
    _add_local_fake(health)
    sessions = sub.add_parser("sessions", help="GET /session metadata only (read-only)")
    sessions.add_argument(
        "--show-directory",
        action="store_true",
        help="print the real directory field (masked by default)",
    )
    _add_local_fake(sessions)
    lifecycle = sub.add_parser(
        "lifecycle",
        help="check an existing serve port (never starts or stops the service)",
    )
    lifecycle.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan only; no network calls",
    )
    _add_local_fake(lifecycle)
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
    return EXIT_CONFIG


if __name__ == "__main__":
    raise SystemExit(main())
