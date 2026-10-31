from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fake_server import FakeOpenCodeServer
from workbench.config import ConfigError, load_config
from workbench.lifecycle import check_lifecycle


def _config(url: str, timeout: str = "5.0"):
    return load_config({
        "OPENCODE_SERVER_PASSWORD": "test-password",
        "OPENCODE_SERVER_USERNAME": "opencode",
        "WORKBENCH_OPENCODE_URL": url,
        "WORKBENCH_TIMEOUT": timeout,
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-S3",
        "WORKBENCH_LEVEL": "L0_LOCAL",
    })


def _closed_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    with FakeOpenCodeServer() as server:
        healthy = check_lifecycle(_config(server.url))
        assert healthy.exit_code == 0 and healthy.ok, healthy
        assert healthy.port_before == "open" and healthy.port_after == "open", healthy
        assert healthy.health_status == 200 and healthy.health_version == "1.19.5", healthy

        closed_url = f"http://127.0.0.1:{_closed_port()}"
        closed = check_lifecycle(_config(closed_url))
        assert closed.exit_code == 6 and not closed.ok, closed
        assert closed.port_before == "closed", closed

        dry = check_lifecycle(_config(closed_url), dry_run=True)
        assert dry.exit_code == 0 and dry.ok and dry.dry_run, dry
        assert dry.port_before == "not-checked", dry

        try:
            _config("http://example.com:4096")
        except ConfigError:
            pass
        else:
            raise AssertionError("non-loopback host was accepted")

        env = os.environ.copy()
        env.update({
            "OPENCODE_SERVER_PASSWORD": "test-password",
            "OPENCODE_SERVER_USERNAME": "opencode",
            "WORKBENCH_OPENCODE_URL": server.url,
            "WORKBENCH_TASK_ID": "TASK-SELFTEST-S3",
            "WORKBENCH_LEVEL": "L0_LOCAL",
        })
        cli_ok = subprocess.run(
            [sys.executable, "run_workbench.py", "lifecycle"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        assert cli_ok.returncode == 0, (cli_ok.returncode, cli_ok.stdout, cli_ok.stderr)
        assert "port_before=open" in cli_ok.stdout and "port_after=open" in cli_ok.stdout
        assert "exit_code=0" in cli_ok.stdout, cli_ok.stdout
        assert "test-password" not in cli_ok.stdout + cli_ok.stderr

        env_closed = env.copy()
        env_closed["WORKBENCH_OPENCODE_URL"] = closed_url
        cli_closed = subprocess.run(
            [sys.executable, "run_workbench.py", "lifecycle"],
            cwd=ROOT, env=env_closed, capture_output=True, text=True, timeout=20,
        )
        assert cli_closed.returncode == 6, (cli_closed.returncode, cli_closed.stdout, cli_closed.stderr)
        assert "port_before=closed" in cli_closed.stdout, cli_closed.stdout

        cli_dry = subprocess.run(
            [sys.executable, "run_workbench.py", "lifecycle", "--dry-run"],
            cwd=ROOT, env=env_closed, capture_output=True, text=True, timeout=20,
        )
        assert cli_dry.returncode == 0, (cli_dry.returncode, cli_dry.stdout, cli_dry.stderr)
        assert "dry-run" in cli_dry.stdout, cli_dry.stdout
        assert "test-password" not in cli_dry.stdout + cli_dry.stderr

        print("PASS S3: existing-port check, 5s cap, exit codes, dry-run no-call")
        print(f"healthy_exit={healthy.exit_code} closed_exit={closed.exit_code} dry_exit={dry.exit_code}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
