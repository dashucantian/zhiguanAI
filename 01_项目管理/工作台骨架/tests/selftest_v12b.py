from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fake_server import FakeOpenCodeServer
from workbench.client import BasicAuthClient
from workbench.config import load_config
from workbench.exit_codes import (
    EXIT_CONNECTION,
    EXIT_OK,
    EXIT_PORT_CLOSED,
)
from workbench.lifecycle import check_lifecycle
from workbench.sessions import list_sessions

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
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-V12B",
        "WORKBENCH_LEVEL": "L0_LOCAL",
    }
    env.update(overrides)
    return load_config(env)


def cli_env(server: FakeOpenCodeServer, level: str | None = None, **overrides) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "WORKBENCH_LEVEL", "WORKBENCH_TIMEOUT", "WORKBENCH_OPENCODE_URL",
        "WORKBENCH_APPROVER", "OPENCODE_URL",
    ):
        env.pop(key, None)
    env.update({
        "OPENCODE_SERVER_PASSWORD": "test-password",
        "OPENCODE_SERVER_USERNAME": "opencode",
        "WORKBENCH_OPENCODE_URL": server.url,
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-V12B",
    })
    if level is not None:
        env["WORKBENCH_LEVEL"] = level
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


def closed_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    with FakeOpenCodeServer() as server:
        server.mode = "sessions"
        client = BasicAuthClient(config_for(server))

        masked = list_sessions(client)
        text = json.dumps(masked.sessions, ensure_ascii=False)
        assert all(session["directory"] == "<masked>" for session in masked.sessions)
        assert "zhiguanAI" not in text, text
        shown = list_sessions(client, show_directory=True)
        assert all(session["directory"] == "D:\\Project\\zhiguanAI" for session in shown.sessions)
        assert "zhiguanAI" in json.dumps(shown.sessions, ensure_ascii=False)

        env = cli_env(server, level="L0_LOCAL")
        default_run = run_cli(["sessions"], env)
        assert default_run.returncode == EXIT_OK, (default_run.returncode, default_run.stderr)
        assert "zhiguanAI" not in default_run.stdout, default_run.stdout
        assert '"<masked>"' in default_run.stdout, default_run.stdout
        shown_run = run_cli(["sessions", "--show-directory"], env)
        assert shown_run.returncode == EXIT_OK, (shown_run.returncode, shown_run.stderr)
        assert "zhiguanAI" in shown_run.stdout, shown_run.stdout
        ok("V4 library default masked; --show-directory is the only release")

        started = time.monotonic()
        normal = check_lifecycle(config_for(server))
        wall_normal = time.monotonic() - started
        assert normal.ok and normal.exit_code == EXIT_OK, normal
        assert wall_normal <= 6.0, wall_normal

        closed_url = f"http://127.0.0.1:{closed_port()}"
        started = time.monotonic()
        closed = check_lifecycle(config_for(server, WORKBENCH_OPENCODE_URL=closed_url))
        wall_closed = time.monotonic() - started
        assert closed.exit_code == EXIT_PORT_CLOSED, closed
        assert wall_closed <= 6.0, wall_closed

        server.mode = "drip"
        started = time.monotonic()
        drip = check_lifecycle(config_for(server))
        wall_drip = time.monotonic() - started
        assert drip.exit_code == EXIT_CONNECTION, drip
        assert wall_drip <= 6.0, wall_drip
        assert drip.error and "deadline" in drip.error.lower(), drip.error
        assert drip.port_after == "not-checked", drip
        print(
            f"V5 normal={wall_normal:.2f}s/exit{normal.exit_code} "
            f"closed={wall_closed:.2f}s/exit{closed.exit_code} "
            f"drip={wall_drip:.2f}s/exit{drip.exit_code} error={drip.error}"
        )
        ok("V5 lifecycle shares one deadline; all three states wall <= 6s")
        server.mode = "sessions"

        original_close = urllib.error.HTTPError.close
        close_calls: list[int] = []

        def counting_close(self):
            close_calls.append(1)
            return original_close(self)

        urllib.error.HTTPError.close = counting_close
        try:
            http_client = BasicAuthClient(config_for(server))
            r401 = http_client.request("GET", "/global/health", auth=False)
            assert r401.status == 401, r401
            server.mode = "error"
            r500 = http_client.request("GET", "/session")
            assert r500.status == 500, r500
            server.mode = "redirect"
            r302 = http_client.request("GET", "/session")
            assert r302.status == 302, r302
            server.mode = "error_drip"
            started = time.monotonic()
            r_drip = http_client.request("GET", "/session")
            wall_http_drip = time.monotonic() - started
            assert r_drip.status == 500, r_drip
            assert wall_http_drip <= 6.0, wall_http_drip
            assert r_drip.error and "timeout" in r_drip.error.lower(), r_drip.error
        finally:
            urllib.error.HTTPError.close = original_close
        assert len(close_calls) == 4, close_calls
        print(
            f"V6 close_calls={len(close_calls)} "
            f"http_error_drip={wall_http_drip:.2f}s/status{r_drip.status}"
        )
        ok("V6 HTTPError.close once per branch (401/500/302/500-drip)")
        server.mode = "sessions"

        bare_env = cli_env(server)
        bare = run_cli(["health"], bare_env)
        assert bare.returncode == EXIT_OK, (bare.returncode, bare.stderr)
        assert "level=L3_EGRESS" in bare.stdout, bare.stdout
        local = run_cli(["health", "--local-fake"], bare_env)
        assert local.returncode == EXIT_OK, (local.returncode, local.stderr)
        assert "level=L0_LOCAL" in local.stdout, local.stdout
        assert "target=http://127.0.0.1:" in local.stdout, local.stdout
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "不会被误读成真实出网" not in readme, "absolute promise still in README"
        assert "--local-fake" in readme, "README missing --local-fake"
        print("V7 bare_level=L3_EGRESS flag_level=L0_LOCAL target_unchanged=1")
        ok("V7 --local-fake declares L0; bare run stays L3 (reverse not done)")

        assert len(PASSED) == 4
        print()
        print("PASS V12B: 4 checks")
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
