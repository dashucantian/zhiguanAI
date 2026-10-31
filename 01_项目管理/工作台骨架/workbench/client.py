from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64
import json
import time
import urllib.error
import urllib.request

from .config import WorkbenchConfig

ALLOWED_PATHS = frozenset({"/global/health", "/session"})
MAX_RESPONSE_BYTES = 1024 * 1024
READ_CHUNK = 64 * 1024


class ClientError(ValueError):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirect rejected: {newurl}",
            headers,
            fp,
        )


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


def _read_limited(source, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        chunk = source.read(min(READ_CHUNK, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


class BasicAuthClient:
    def __init__(self, config: WorkbenchConfig):
        self.config = config
        token = base64.b64encode(
            f"{config.username}:{config.password}".encode("utf-8")
        ).decode("ascii")
        self._auth_header = f"Basic {token}"
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirectHandler(),
        )

    def request(self, method: str, path: str, auth: bool = True) -> HttpResponse:
        if method != "GET":
            raise ClientError(f"method not allowed: {method}")
        if path not in ALLOWED_PATHS:
            raise ClientError(f"path not allowed: {path}")

        url = self.config.base_url + path
        req = urllib.request.Request(url, method=method)
        if auth:
            req.add_header("Authorization", self._auth_header)
        started = time.monotonic()
        try:
            with self._opener.open(req, timeout=self.config.timeout) as resp:
                raw = _read_limited(resp, MAX_RESPONSE_BYTES)
                elapsed = int((time.monotonic() - started) * 1000)
                if len(raw) > MAX_RESPONSE_BYTES:
                    return HttpResponse(
                        status=resp.status,
                        body="",
                        elapsed_ms=elapsed,
                        error=f"response body exceeds {MAX_RESPONSE_BYTES} bytes",
                    )
                return HttpResponse(
                    status=resp.status,
                    body=raw.decode("utf-8", errors="replace"),
                    elapsed_ms=elapsed,
                )
        except urllib.error.HTTPError as exc:
            body = ""
            if exc.fp is not None:
                raw = _read_limited(exc, MAX_RESPONSE_BYTES)
                if len(raw) <= MAX_RESPONSE_BYTES:
                    body = raw.decode("utf-8", errors="replace")
            if 300 <= exc.code < 400:
                error = f"redirect rejected (HTTP {exc.code})"
            else:
                error = f"HTTP {exc.code}"
            return HttpResponse(
                status=exc.code,
                body=body,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=error,
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
    if resp.error:
        return HealthResult(
            ok=False,
            status=resp.status,
            version=None,
            error=resp.error,
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


def _safe_field(value, max_len: int = 64) -> str:
    text = str(value).replace("\r", "_").replace("\n", "_").replace("|", "_")
    return text[:max_len]


def format_log_line(
    config: WorkbenchConfig,
    action: str,
    status: int | None,
    elapsed_ms: int,
    version: str | None = None,
    summary: str | None = None,
    approver: str | None = None,
) -> str:
    channel = "opencode serve" + (f" {_safe_field(version, 32)}" if version else "")
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    summary_value = _safe_field(summary, 96) if summary else "-"
    approver_value = _safe_field(
        config.approver if approver is None else approver, 32
    ) or "-"
    return (
        f"task={_safe_field(config.task_id)} time={timestamp} "
        f"channel={channel} action={_safe_field(action, 32)} http={status} "
        f"summary={summary_value} level={_safe_field(config.level)} "
        f"approver={approver_value} target={_safe_field(config.safe_url, 128)} "
        f"elapsed_ms={elapsed_ms}"
    )
