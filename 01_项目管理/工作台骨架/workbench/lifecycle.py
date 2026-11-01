from __future__ import annotations

from dataclasses import dataclass
import socket
import time

from .client import BasicAuthClient, check_health
from .config import WorkbenchConfig
from .exit_codes import EXIT_CONNECTION, EXIT_HTTP, EXIT_OK, EXIT_PORT_CLOSED

PORT_CHECK_TIMEOUT = 5.0
MIN_PORT_RECHECK = 0.1


@dataclass(frozen=True)
class LifecycleResult:
    ok: bool
    exit_code: int
    dry_run: bool
    port_before: str
    port_after: str
    health_status: int | None
    health_version: str | None
    error: str | None
    health_elapsed_ms: int | None = None


def port_open(host: str, port: int, timeout: float = PORT_CHECK_TIMEOUT) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_lifecycle(config: WorkbenchConfig, dry_run: bool = False) -> LifecycleResult:
    if dry_run:
        return LifecycleResult(
            ok=True,
            exit_code=EXIT_OK,
            dry_run=True,
            port_before="not-checked",
            port_after="not-checked",
            health_status=None,
            health_version=None,
            error=None,
        )

    host = config.host or ""
    started = time.monotonic()
    deadline = started + config.timeout
    port_timeout = min(config.timeout, PORT_CHECK_TIMEOUT)
    before = port_open(host, config.port, port_timeout)
    if not before:
        return LifecycleResult(
            ok=False,
            exit_code=EXIT_PORT_CLOSED,
            dry_run=False,
            port_before="closed",
            port_after="not-checked",
            health_status=None,
            health_version=None,
            error="port closed",
        )

    remaining = deadline - time.monotonic()
    if remaining < MIN_PORT_RECHECK:
        return LifecycleResult(
            ok=False,
            exit_code=EXIT_CONNECTION,
            dry_run=False,
            port_before="open",
            port_after="not-checked",
            health_status=None,
            health_version=None,
            error="lifecycle deadline exceeded",
        )

    health = check_health(BasicAuthClient(config), auth=True, deadline=deadline)
    remaining = deadline - time.monotonic()
    # Too little budget left: do not run a doomed recheck and report "closed".
    if remaining < MIN_PORT_RECHECK:
        return LifecycleResult(
            ok=False,
            exit_code=EXIT_CONNECTION,
            dry_run=False,
            port_before="open",
            port_after="not-checked",
            health_status=health.status,
            health_version=health.version,
            error="lifecycle deadline exceeded",
            health_elapsed_ms=health.elapsed_ms,
        )
    after = port_open(host, config.port, remaining)
    if not health.ok:
        if health.status is None:
            exit_code = EXIT_CONNECTION
        else:
            exit_code = EXIT_HTTP
        return LifecycleResult(
            ok=False,
            exit_code=exit_code,
            dry_run=False,
            port_before="open",
            port_after="open" if after else "closed",
            health_status=health.status,
            health_version=health.version,
            error=health.error,
            health_elapsed_ms=health.elapsed_ms,
        )
    if not after:
        return LifecycleResult(
            ok=False,
            exit_code=EXIT_CONNECTION,
            dry_run=False,
            port_before="open",
            port_after="closed",
            health_status=health.status,
            health_version=health.version,
            error="port closed after health",
            health_elapsed_ms=health.elapsed_ms,
        )
    return LifecycleResult(
        ok=True,
        exit_code=EXIT_OK,
        dry_run=False,
        port_before="open",
        port_after="open",
        health_status=health.status,
        health_version=health.version,
        error=None,
        health_elapsed_ms=health.elapsed_ms,
    )
