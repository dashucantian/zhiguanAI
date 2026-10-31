from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64
import json
import time
import urllib.error
import urllib.request

from .config import WorkbenchConfig


@dataclass(frozen=True)
class HttpResponse:
    status: int | None
    body: str
    elapsed_ms: int
    error: str | None = None


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    status: int | None
    version: str | None
    error: str | None
    elapsed_ms: int


class BasicAuthClient:
    def __init__(self, config: WorkbenchConfig):
        self.config = config
        token = base64.b64encode(
            f"{config.username}:{config.password}".encode("utf-8")
        ).decode("ascii")
        self._auth_header = f"Basic {token}"

    def request(self, method: str, path: str, auth: bool = True) -> HttpResponse:
        url = self.config.base_url + path
        req = urllib.request.Request(url, method=method)
        if auth:
            req.add_header("Authorization", self._auth_header)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return HttpResponse(
                    status=resp.status,
                    body=body,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
        except urllib.error.HTTPError as exc:
            body = ""
            if exc.fp is not None:
                body = exc.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status=exc.code,
                body=body,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=f"HTTP {exc.code}",
            )
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            return HttpResponse(
                status=None,
                body="",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=f"connection error: {reason}",
            )
        except TimeoutError as exc:
            return HttpResponse(
                status=None,
                body="",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=f"timeout: {exc}",
            )


def check_health(client: BasicAuthClient, auth: bool = True) -> HealthResult:
    resp = client.request("GET", "/global/health", auth=auth)
    if resp.status != 200:
        return HealthResult(
            ok=False,
            status=resp.status,
            version=None,
            error=resp.error or (f"HTTP {resp.status}" if resp.status else "no response"),
            elapsed_ms=resp.elapsed_ms,
        )
    try:
        data = json.loads(resp.body)
    except json.JSONDecodeError as exc:
        return HealthResult(
            ok=False,
            status=resp.status,
            version=None,
            error=f"JSON decode error: {exc.msg}",
            elapsed_ms=resp.elapsed_ms,
        )
    if not isinstance(data, dict) or data.get("healthy") is not True:
        return HealthResult(
            ok=False,
            status=resp.status,
            version=None,
            error="unexpected health payload",
            elapsed_ms=resp.elapsed_ms,
        )
    version = data.get("version")
    if not isinstance(version, str):
        return HealthResult(
            ok=False,
            status=resp.status,
            version=None,
            error="health payload has no string version",
            elapsed_ms=resp.elapsed_ms,
        )
    return HealthResult(
        ok=True,
        status=resp.status,
        version=version,
        error=None,
        elapsed_ms=resp.elapsed_ms,
    )


def format_log_line(
    config: WorkbenchConfig,
    action: str,
    status: int | None,
    elapsed_ms: int,
    version: str | None = None,
) -> str:
    channel = "opencode serve" + (f" {version}" if version else "")
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return (
        f"task={config.task_id} time={timestamp} channel={channel} "
        f"action={action} http={status} elapsed_ms={elapsed_ms} level={config.level}"
    )
