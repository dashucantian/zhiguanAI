from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fake_server import FakeOpenCodeServer
from workbench.client import BasicAuthClient, check_health
from workbench.config import ConfigError, WorkbenchConfig, load_config
from workbench.exit_codes import EXIT_CONFIG, EXIT_OK

PASSED: list[str] = []


def ok(name: str) -> None:
    PASSED.append(name)
    print(f"PASS {name}")


def config_for(server: FakeOpenCodeServer, **overrides):
    env = {
        "OPENCODE_SERVER_PASSWORD": "test-password",
        "OPENCODE_SERVER_USERNAME": "opencode",
        "WORKBENCH_OPENCODE_URL": server.url,
        "WORKBENCH_TIMEOUT": "5.0",
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-V12",
        "WORKBENCH_LEVEL": "L0_LOCAL",
    }
    env.update(overrides)
    return load_config(env)


def cli_env(server: FakeOpenCodeServer, **overrides) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "OPENCODE_SERVER_PASSWORD": "test-password",
        "OPENCODE_SERVER_USERNAME": "opencode",
        "WORKBENCH_OPENCODE_URL": server.url,
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-V12",
        "WORKBENCH_LEVEL": "L0_LOCAL",
    })
    env.update(overrides)
    return env


def run_cli(args: list[str], env: dict[str, str]):
    return subprocess.run(
        [sys.executable, str(ROOT / "run_workbench.py"), *args],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    with FakeOpenCodeServer() as server:
        baseline = check_health(BasicAuthClient(config_for(server)))
        assert baseline.ok and baseline.status == 200, baseline
        ok("V12 baseline: normal health still 200")

        server.mode = "drip"
        started = time.monotonic()
        result = check_health(BasicAuthClient(config_for(server)))
        wall = time.monotonic() - started
        assert not result.ok, result
        assert wall <= 6.0, wall
        assert result.elapsed_ms <= 6000, result.elapsed_ms
        assert result.status is None, result
        assert result.error and "timeout" in result.error.lower(), result.error
        print(
            f"V1 wall={wall:.2f}s elapsed_ms={result.elapsed_ms} "
            f"status={result.status} error={result.error}"
        )
        ok("V1 deadline: drip 12B at 1B/s stopped under 6s wall / 6000ms elapsed")

        server.mode = "sessions"
        before = len(server.requests)
        for suffix in ("?", "#"):
            url = server.url + suffix
            try:
                WorkbenchConfig(base_url=url, username="opencode", password="x")
            except ConfigError:
                pass
            else:
                raise AssertionError(f"direct construction accepted {url}")
            try:
                config_for(server, WORKBENCH_OPENCODE_URL=url)
            except ConfigError:
                pass
            else:
                raise AssertionError(f"load_config accepted {url}")
            run = run_cli(["health"], cli_env(server, WORKBENCH_OPENCODE_URL=url))
            assert run.returncode == EXIT_CONFIG, (url, run.returncode, run.stderr)
            assert "config error" in run.stderr, run.stderr
            assert "Traceback" not in run.stderr, run.stderr
        assert len(server.requests) == before, server.requests[before:]
        ok("V2 empty separator: '?' and '#' rejected locally; CLI RC=4; zero new requests")

        for timeout in (float("nan"), float("inf")):
            try:
                WorkbenchConfig(
                    base_url=server.url,
                    username="opencode",
                    password="x",
                    timeout=timeout,
                )
            except ConfigError:
                pass
            else:
                raise AssertionError(f"direct construction accepted timeout={timeout}")
        for raw in ("nan", "inf"):
            try:
                config_for(server, WORKBENCH_TIMEOUT=raw)
            except ConfigError:
                pass
            else:
                raise AssertionError(f"load_config accepted WORKBENCH_TIMEOUT={raw}")
        before = len(server.requests)
        run = run_cli(["health"], cli_env(server, WORKBENCH_TIMEOUT="nan"))
        assert run.returncode == EXIT_CONFIG, (run.returncode, run.stderr)
        assert "config error" in run.stderr, run.stderr
        assert "Traceback" not in run.stderr, run.stderr
        assert len(server.requests) == before, server.requests[before:]
        ok("V3 nan/inf timeout rejected at config; CLI RC=4 without traceback")

        final = check_health(BasicAuthClient(config_for(server)))
        assert final.ok and final.status == 200, final
        assert len(PASSED) == 4
        print()
        print("PASS V12: 4 checks")
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
