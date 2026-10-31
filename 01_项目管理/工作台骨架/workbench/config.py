from __future__ import annotations

from dataclasses import dataclass, field
import os
from urllib.parse import urlparse

DEFAULT_BASE_URL = "http://127.0.0.1:4096"
DEFAULT_USERNAME = "opencode"
DEFAULT_TIMEOUT = 5.0
DEFAULT_TASK_ID = "TASK-20261031-05"
DEFAULT_LEVEL = "L3_EGRESS"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class WorkbenchConfig:
    base_url: str
    username: str
    password: str = field(repr=False)
    timeout: float = DEFAULT_TIMEOUT
    task_id: str = DEFAULT_TASK_ID
    level: str = DEFAULT_LEVEL

    @property
    def parsed(self):
        return urlparse(self.base_url)

    @property
    def scheme(self) -> str:
        return self.parsed.scheme

    @property
    def host(self) -> str | None:
        return self.parsed.hostname

    @property
    def port(self) -> int:
        return self.parsed.port or (443 if self.scheme == "https" else 4096)

    @property
    def safe_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def __str__(self) -> str:
        return (
            f"WorkbenchConfig(url={self.safe_url}, user={self.username}, "
            f"timeout={self.timeout}, task={self.task_id}, level={self.level})"
        )


def load_config(env: dict[str, str] | None = None) -> WorkbenchConfig:
    env = os.environ if env is None else env
    base_url = env.get("WORKBENCH_OPENCODE_URL") or env.get("OPENCODE_URL") or DEFAULT_BASE_URL
    username = env.get("OPENCODE_SERVER_USERNAME") or DEFAULT_USERNAME
    password = env.get("OPENCODE_SERVER_PASSWORD")
    if not password:
        raise ConfigError(
            "OPENCODE_SERVER_PASSWORD is required (environment variable only; never a CLI argument)"
        )

    timeout_raw = env.get("WORKBENCH_TIMEOUT", str(DEFAULT_TIMEOUT))
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise ConfigError(f"WORKBENCH_TIMEOUT must be a number, got {timeout_raw!r}") from exc
    if timeout <= 0:
        raise ConfigError("WORKBENCH_TIMEOUT must be greater than zero")

    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise ConfigError(f"unsupported scheme: {parsed.scheme or '<empty>'}")
    if not parsed.hostname:
        raise ConfigError("base URL must include a host")
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise ConfigError(f"non-loopback host rejected: {parsed.hostname}")
    if parsed.username or parsed.password:
        raise ConfigError("credentials must not be embedded in the base URL; use OPENCODE_SERVER_PASSWORD")

    return WorkbenchConfig(
        base_url=base_url.rstrip("/"),
        username=username,
        password=password,
        timeout=timeout,
        task_id=env.get("WORKBENCH_TASK_ID", DEFAULT_TASK_ID),
        level=env.get("WORKBENCH_LEVEL", DEFAULT_LEVEL),
    )
