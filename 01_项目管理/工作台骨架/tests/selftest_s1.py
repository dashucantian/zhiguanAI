from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fake_server import FakeOpenCodeServer
from workbench.client import BasicAuthClient, check_health, format_log_line
from workbench.config import ConfigError, load_config


def main() -> int:
    with FakeOpenCodeServer() as server:
        env = {
            "OPENCODE_SERVER_PASSWORD": "test-password",
            "OPENCODE_SERVER_USERNAME": "opencode",
            "WORKBENCH_OPENCODE_URL": server.url,
            "WORKBENCH_TASK_ID": "TASK-SELFTEST-S1",
            "WORKBENCH_LEVEL": "L3_EGRESS",
        }
        config = load_config(env)
        client = BasicAuthClient(config)

        ok = check_health(client, auth=True)
        assert ok.ok and ok.status == 200 and ok.version == "1.19.5", ok
        line = format_log_line(config, "health", ok.status, ok.elapsed_ms, ok.version)
        assert "http=200" in line and "test-password" not in line, line

        denied = check_health(client, auth=False)
        assert denied.status == 401 and not denied.ok, denied
        denied_line = format_log_line(config, "health-noauth", denied.status, denied.elapsed_ms)
        assert "http=401" in denied_line and "test-password" not in denied_line, denied_line

        try:
            load_config({})
        except ConfigError:
            pass
        else:
            raise AssertionError("missing password was accepted")

        try:
            load_config({
                "OPENCODE_SERVER_PASSWORD": "x",
                "WORKBENCH_OPENCODE_URL": "http://example.com:4096",
            })
        except ConfigError:
            pass
        else:
            raise AssertionError("non-loopback host was accepted")

        child_env = os.environ.copy()
        child_env.update(env)
        cli_ok = subprocess.run(
            [sys.executable, "run_workbench.py", "health"],
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert cli_ok.returncode == 0, (cli_ok.returncode, cli_ok.stdout, cli_ok.stderr)
        assert "http=200" in cli_ok.stdout and "version=1.19.5" in cli_ok.stdout, cli_ok.stdout
        assert "test-password" not in cli_ok.stdout + cli_ok.stderr

        cli_denied = subprocess.run(
            [sys.executable, "run_workbench.py", "health", "--no-auth"],
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert cli_denied.returncode == 2, (cli_denied.returncode, cli_denied.stdout, cli_denied.stderr)
        assert "http=401" in cli_denied.stdout, cli_denied.stdout
        assert "test-password" not in cli_denied.stdout + cli_denied.stderr

        print("PASS S1: auth 200 / no-auth 401; config loopback + env-password enforced")
        print(line)
        print(denied_line)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
