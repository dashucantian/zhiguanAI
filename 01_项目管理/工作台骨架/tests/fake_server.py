from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class FakeOpenCodeServer:
    """Local loopback fake for self-tests. It never leaves 127.0.0.1."""

    def __init__(self, username: str = "opencode", password: str = "test-password"):
        self.username = username
        self.password = password
        self.mode = "sessions"
        self.requests: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                return

            def _authorized(self) -> bool:
                expected = "Basic " + base64.b64encode(
                    f"{outer.username}:{outer.password}".encode("utf-8")
                ).decode("ascii")
                return self.headers.get("Authorization") == expected

            def _send(self, status: int, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def do_GET(self):
                outer.requests.append(self.path)
                if not self._authorized():
                    self._send(401, "")
                    return
                if self.path == "/global/health":
                    self._send(200, json.dumps({"healthy": True, "version": "1.19.5"}))
                    return
                if self.path == "/session":
                    if outer.mode == "empty":
                        self._send(200, "[]")
                    elif outer.mode == "error":
                        self._send(500, json.dumps({"error": "boom"}))
                    elif outer.mode == "badjson":
                        self._send(200, "not json")
                    elif outer.mode == "slow":
                        time.sleep(0.6)
                        self._send(200, "[]")
                    else:
                        self._send(200, json.dumps(self._sessions()))
                    return
                self._send(404, json.dumps({"error": "not found"}))

            def _sessions(self):
                return [
                    {
                        "id": f"ses_test_{index}",
                        "parentID": None,
                        "projectID": "proj_test",
                        "directory": "D:\\Project\\zhiguanAI",
                        "version": "1.19.5",
                        "time": {"created": index, "updated": index + 10},
                        "title": f"DECOY_TITLE_{index}",
                        "summary": f"DECOY_SUMMARY_{index}",
                        "slug": f"decoy-slug-{index}",
                        "cost": 1,
                        "tokens": {"input": 1, "output": 1},
                        "agent": "decoy-agent",
                        "model": "decoy-model",
                    }
                    for index in (1, 2, 3)
                ]

        self.httpd = _Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeOpenCodeServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def __enter__(self) -> "FakeOpenCodeServer":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
