from __future__ import annotations

from dataclasses import dataclass
import json

from .client import BasicAuthClient

ALLOWED_SESSION_FIELDS = ("id", "parentID", "projectID", "directory", "version")
ALLOWED_TIME_FIELDS = ("created", "updated")


class SessionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionListResult:
    status: int
    elapsed_ms: int
    sessions: list[dict]


def parse_sessions(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SessionError(
            f"JSON decode error: {exc.msg} (line {exc.lineno}, column {exc.colno})"
        ) from exc

    if not isinstance(data, list):
        raise SessionError(f"unexpected top-level type: {type(data).__name__}")

    sessions: list[dict] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise SessionError(f"session[{index}] is not an object")
        meta = {field: item.get(field) for field in ALLOWED_SESSION_FIELDS}
        time_value = item.get("time")
        if isinstance(time_value, dict):
            meta["time"] = {field: time_value.get(field) for field in ALLOWED_TIME_FIELDS}
        else:
            meta["time"] = None
        # Explicit allowlist: title, summary and every other field are dropped.
        sessions.append(meta)
    return sessions


def list_sessions(client: BasicAuthClient) -> SessionListResult:
    resp = client.request("GET", "/session")
    if resp.status is None:
        raise SessionError(resp.error or "no response")
    if resp.status != 200:
        raise SessionError(f"HTTP {resp.status}: {resp.error or 'non-200'}")
    return SessionListResult(
        status=resp.status,
        elapsed_ms=resp.elapsed_ms,
        sessions=parse_sessions(resp.body),
    )
