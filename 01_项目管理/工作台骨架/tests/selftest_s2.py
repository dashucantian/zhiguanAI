from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fake_server import FakeOpenCodeServer
from workbench.client import BasicAuthClient
from workbench.config import load_config
from workbench.sessions import SessionError, list_sessions


def _config(server, timeout="5.0"):
    return load_config({
        "OPENCODE_SERVER_PASSWORD": "test-password",
        "OPENCODE_SERVER_USERNAME": "opencode",
        "WORKBENCH_OPENCODE_URL": server.url,
        "WORKBENCH_TIMEOUT": timeout,
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-S2",
        "WORKBENCH_LEVEL": "L0_LOCAL",
    })


def main() -> int:
    with FakeOpenCodeServer() as server:
        client = BasicAuthClient(_config(server))

        result = list_sessions(client)
        assert result.status == 200 and len(result.sessions) == 3, result
        expected_keys = {"id", "parentID", "projectID", "directory", "version", "time"}
        for session in result.sessions:
            assert set(session.keys()) == expected_keys, session
            assert set(session["time"].keys()) == {"created", "updated"}, session
            assert "title" not in session and "summary" not in session, session
        assert all("DECOY" not in str(session) for session in result.sessions), result.sessions

        server.mode = "empty"
        assert list_sessions(client).sessions == []

        server.mode = "error"
        try:
            list_sessions(client)
        except SessionError as exc:
            assert "HTTP 500" in str(exc), exc
        else:
            raise AssertionError("HTTP 500 did not raise")

        server.mode = "badjson"
        try:
            list_sessions(client)
        except SessionError as exc:
            assert "JSON decode error" in str(exc), exc
        else:
            raise AssertionError("bad JSON did not raise")

        server.mode = "slow"
        slow_client = BasicAuthClient(_config(server, timeout="0.2"))
        try:
            list_sessions(slow_client)
        except SessionError as exc:
            message = str(exc).lower()
            assert "timed out" in message or "timeout" in message, exc
        else:
            raise AssertionError("timeout did not raise")

        env = os.environ.copy()
        env.update({
            "OPENCODE_SERVER_PASSWORD": "test-password",
            "OPENCODE_SERVER_USERNAME": "opencode",
            "WORKBENCH_OPENCODE_URL": server.url,
            "WORKBENCH_TASK_ID": "TASK-SELFTEST-S2",
            "WORKBENCH_LEVEL": "L0_LOCAL",
        })

        server.mode = "sessions"
        cli_ok = subprocess.run(
            [sys.executable, "run_workbench.py", "sessions"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        assert cli_ok.returncode == 0, (cli_ok.returncode, cli_ok.stdout, cli_ok.stderr)
        assert "ses_test_1" in cli_ok.stdout, cli_ok.stdout
        assert "summary=sessions=3" in cli_ok.stdout, cli_ok.stdout
        assert '"<masked>"' in cli_ok.stdout and "D:\\\\Project\\\\zhiguanAI" not in cli_ok.stdout
        assert "DECOY_TITLE" not in cli_ok.stdout and "DECOY_SUMMARY" not in cli_ok.stdout
        assert "test-password" not in cli_ok.stdout + cli_ok.stderr

        server.mode = "error"
        cli_error = subprocess.run(
            [sys.executable, "run_workbench.py", "sessions"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        assert cli_error.returncode == 2, (cli_error.returncode, cli_error.stdout, cli_error.stderr)
        assert "HTTP 500" in cli_error.stderr, cli_error.stderr

        server.mode = "badjson"
        cli_bad = subprocess.run(
            [sys.executable, "run_workbench.py", "sessions"],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )
        assert cli_bad.returncode == 5, (cli_bad.returncode, cli_bad.stdout, cli_bad.stderr)
        assert "JSON decode error" in cli_bad.stderr, cli_bad.stderr

        server.mode = "slow"
        env_slow = env.copy()
        env_slow["WORKBENCH_TIMEOUT"] = "0.2"
        cli_slow = subprocess.run(
            [sys.executable, "run_workbench.py", "sessions"],
            cwd=ROOT, env=env_slow, capture_output=True, text=True, timeout=20,
        )
        assert cli_slow.returncode == 3, (cli_slow.returncode, cli_slow.stdout, cli_slow.stderr)

        print("PASS S2: metadata allowlist, empty/500/bad-json/timeout paths; title/summary dropped")
        print(result.sessions[0])
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
