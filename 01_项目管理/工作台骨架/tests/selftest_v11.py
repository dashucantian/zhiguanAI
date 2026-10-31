from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fake_server import FakeOpenCodeServer
from workbench.client import BasicAuthClient, ClientError, check_health, format_log_line
from workbench.config import ConfigError, WorkbenchConfig, load_config
from workbench.exit_codes import (
    EXIT_CONFIG,
    EXIT_CONNECTION,
    EXIT_HTTP,
    EXIT_OK,
    EXIT_PORT_CLOSED,
    EXIT_PROTOCOL,
)
from workbench.sessions import SessionError, list_sessions

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
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-V11",
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
        "WORKBENCH_TASK_ID": "TASK-SELFTEST-V11",
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


def closed_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    with FakeOpenCodeServer() as server:
        base_config = config_for(server)
        client = BasicAuthClient(base_config)
        healthy = check_health(client)
        assert healthy.ok and healthy.status == 200, healthy
        ok("P0 baseline: loopback fake returns 200")

        saved = {}
        for key in (
            "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
            "all_proxy", "ALL_PROXY", "no_proxy", "NO_PROXY",
        ):
            saved[key] = os.environ.get(key)
        try:
            for key in (
                "http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY",
            ):
                os.environ[key] = "http://127.0.0.1:1"
            os.environ["no_proxy"] = ""
            os.environ["NO_PROXY"] = ""
            proxied = BasicAuthClient(config_for(server))
            result = check_health(proxied)
            assert result.ok and result.version == "1.19.5", result
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        ok("P1-1a dead HTTP(S)_PROXY set: request still goes direct, 200")

        server.mode = "redirect"
        before = len(server.requests)
        resp = client.request("GET", "/session")
        assert resp.status == 302, resp
        assert resp.error and "redirect rejected" in resp.error, resp
        try:
            list_sessions(client)
        except SessionError as exc:
            assert "redirect rejected" in str(exc), exc
        else:
            raise AssertionError("cross-host 302 was followed")
        assert len(server.requests) == before + 2, server.requests[before:]
        ok("P1-1b cross-host 302 rejected, never followed")

        server.mode = "sessions"
        before = len(server.requests)
        for method, path in (
            ("POST", "/session"),
            ("DELETE", "/session"),
            ("GET", "/session/ses_test_1"),
            ("GET", "/global/health/../session"),
            ("GET", "//example.com/session"),
        ):
            try:
                client.request(method, path)
            except ClientError:
                pass
            else:
                raise AssertionError(f"{method} {path} was not rejected")
        assert len(server.requests) == before, server.requests[before:]
        ok("P1-2 GET-only + path whitelist reject locally (5/5, zero requests)")

        for kwargs in (
            {"base_url": "http://example.com:4096", "username": "opencode", "password": "x"},
            {"base_url": "http://127.0.0.1:4096", "username": "opencode", "password": ""},
            {"base_url": "http://127.0.0.1:4096", "username": "", "password": "x"},
            {"base_url": "http://127.0.0.1:4096/api", "username": "opencode", "password": "x"},
            {"base_url": "http://127.0.0.1:4096?x=1", "username": "opencode", "password": "x"},
        ):
            try:
                WorkbenchConfig(**kwargs)
            except ConfigError:
                pass
            else:
                raise AssertionError(f"direct construction accepted: {kwargs}")
        ok("P1-3 direct construction rejects non-loopback / empty password / base path or query")

        server.mode = "large"
        try:
            list_sessions(client)
        except SessionError as exc:
            assert "exceeds" in str(exc), exc
        else:
            raise AssertionError("2 MiB response body was accepted")
        ok("P1-4 2 MiB response rejected at the 1 MiB cap")

        clamped = WorkbenchConfig(
            base_url=server.url, username="opencode", password="x", timeout=30
        )
        assert clamped.timeout == 5.0, clamped
        assert config_for(server, WORKBENCH_TIMEOUT="30").timeout == 5.0
        for bad in ("0", "-1", "abc"):
            try:
                config_for(server, WORKBENCH_TIMEOUT=bad)
            except ConfigError:
                pass
            else:
                raise AssertionError(f"timeout {bad!r} was accepted")
        ok("P1-5 timeout clamped to 5.0; non-positive/non-numeric rejected")

        server.mode = "sessions"
        env = cli_env(server)
        masked_run = run_cli(["sessions"], env)
        assert masked_run.returncode == EXIT_OK, (masked_run.returncode, masked_run.stderr)
        assert '"<masked>"' in masked_run.stdout, masked_run.stdout
        assert "D:\\\\Project\\\\zhiguanAI" not in masked_run.stdout, masked_run.stdout
        shown_run = run_cli(["sessions", "--show-directory"], env)
        assert shown_run.returncode == EXIT_OK, (shown_run.returncode, shown_run.stderr)
        assert "D:\\\\Project\\\\zhiguanAI" in shown_run.stdout, shown_run.stdout
        ok("P1-6 directory masked by default; --show-directory reveals it")

        closed_url = f"http://127.0.0.1:{closed_port()}"
        env_closed = cli_env(server, WORKBENCH_OPENCODE_URL=closed_url)
        closed_lifecycle = run_cli(["lifecycle"], env_closed)
        assert closed_lifecycle.returncode == EXIT_PORT_CLOSED, (
            closed_lifecycle.returncode, closed_lifecycle.stdout, closed_lifecycle.stderr
        )
        closed_health = run_cli(["health"], env_closed)
        assert closed_health.returncode == EXIT_CONNECTION, (
            closed_health.returncode, closed_health.stdout, closed_health.stderr
        )
        no_auth = run_cli(["health", "--no-auth"], env)
        assert no_auth.returncode == EXIT_HTTP, (no_auth.returncode, no_auth.stderr)
        server.mode = "error"
        http_error = run_cli(["sessions"], env)
        assert http_error.returncode == EXIT_HTTP, (http_error.returncode, http_error.stderr)
        server.mode = "badjson"
        bad_json = run_cli(["sessions"], env)
        assert bad_json.returncode == EXIT_PROTOCOL, (bad_json.returncode, bad_json.stderr)
        bad_port = run_cli(
            ["health"],
            cli_env(server, WORKBENCH_OPENCODE_URL="http://127.0.0.1:notaport"),
        )
        assert bad_port.returncode == EXIT_CONFIG, (bad_port.returncode, bad_port.stderr)
        assert "config error" in bad_port.stderr and "Traceback" not in bad_port.stderr
        ok("P1-7 exit codes: 6 port closed / 3 connection / 2 HTTP-auth / 5 protocol / 4 config")

        fake_line = format_log_line(
            base_config, "health", 200, 1,
            version="1.19.5", summary="version=1.19.5",
        )
        assert "level=L0_LOCAL" in fake_line, fake_line
        assert "target=http://127.0.0.1:" in fake_line, fake_line
        real_config = load_config({
            "OPENCODE_SERVER_PASSWORD": "test-password",
            "WORKBENCH_OPENCODE_URL": server.url,
        })
        assert real_config.level == "L3_EGRESS", real_config
        real_line = format_log_line(real_config, "health", 200, 1, version="1.19.5")
        assert "level=L3_EGRESS" in real_line, real_line
        ok("P1-8 fake self-test=L0_LOCAL, default real call=L3_EGRESS, target= present")

        custom = format_log_line(
            base_config, "health", 200, 1,
            summary="version=1.19.5", approver="W3",
        )
        assert "summary=version=1.19.5" in custom and "approver=W3" in custom, custom
        empty_approver = format_log_line(base_config, "health", 200, 1, approver="")
        assert "approver=-" in empty_approver, empty_approver
        ok("LOG-8 eight segments: summary and approver populated (empty -> -)")

        for kwargs in (
            {"task_id": "TASK\nINJECT"},
            {"level": "L3|EGRESS"},
            {"task_id": "T" * 65},
        ):
            try:
                WorkbenchConfig(
                    base_url=server.url, username="opencode", password="x", **kwargs
                )
            except ConfigError:
                pass
            else:
                raise AssertionError(f"log field accepted: {kwargs}")
        long_line = format_log_line(
            base_config, "a" * 200, 200, 1,
            version="1.19.5\nx|y", summary="a\nb|c" * 20,
        )
        assert "\n" not in long_line, long_line
        action = long_line.split(" action=", 1)[1].split(" ", 1)[0]
        assert len(action) <= 32, action
        summary = long_line.split(" summary=", 1)[1].split(" level=", 1)[0]
        assert len(summary) <= 96 and "|" not in summary and "a_b_c" in summary, summary
        ok("P2-9 log fields whitelisted and truncated; no newline/pipe injection")

        for url in ("http://127.0.0.1:notaport", "http://127.0.0.1:70000"):
            try:
                config_for(server, WORKBENCH_OPENCODE_URL=url)
            except ConfigError as exc:
                assert "port" in str(exc).lower(), exc
            else:
                raise AssertionError(f"invalid port accepted: {url}")
        ok("P2-10 invalid port -> ConfigError (no bare ValueError)")

        fallback = subprocess.run(
            [sys.executable, "-P", str(ROOT / "run_workbench.py"), "health"],
            cwd=str(ROOT),
            env=cli_env(server),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert fallback.returncode == EXIT_OK, (
            fallback.returncode, fallback.stdout, fallback.stderr
        )
        assert "version=1.19.5" in fallback.stdout, fallback.stdout
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "Python 3.12" in readme and "sys.path" in readme, "README interpreter note missing"
        assert "/session/:id" in readme, "README contract table row missing"
        ok("P2-11 sys.path fallback verified with python -P; README notes present")

        print()
        print(f"PASS V11: {len(PASSED)} checks")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
