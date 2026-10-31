from __future__ import annotations

from dataclasses import dataclass
import socket

from .client import BasicAuthClient, check_health
from .config import WorkbenchConfig

PORT_CHECK_TIMEOUT = 5.0


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
            exit_code=0,
            dry_run=True,
            port_before="not-checked",
            port_after="not-checked",
            health_status=None,
            health_version=None,
            error=None,
        )

    host = config.host or ""
    timeout = min(config.timeout, PORT_CHECK_TIMEOUT)
    before = port_open(host, config.port, timeout)
    if not before:
        return LifecycleResult(
            ok=False,
            exit_code=2,
            dry_run=False,
            port_before="closed",
            port_after="not-checked",
            health_status=None,
            health_version=None,
            error="port closed",
        )

    health = check_health(BasicAuthClient(config), auth=True)
    after = port_open(host, config.port, timeout)
    if not health.ok:
        return LifecycleResult(
            ok=False,
            exit_code=3,
            dry_run=False,
            port_before="open",
            port_after="open" if after else "closed",
            health_status=health.status,
            health_version=health.version,
            error=health.error,
        )
    if not after:
        return LifecycleResult(
            ok=False,
            exit_code=3,
            dry_run=False,
            port_before="open",
            port_after="closed",
            health_status=health.status,
            health_version=health.version,
            error="port closed after health",
        )
    return LifecycleResult(
        ok=True,
        exit_code=0,
        dry_run=False,
        port_before="open",
        port_after="open",
        health_status=health.status,
        health_version=health.version,
        error=None,
    )
