"""Qoder 客户端窗口桥：把一次提问交给本机的 Qoder 客户端回答，再包成 OpenAI 兼容接口。

为什么要有这个桥：飞书群里显示的说话人永远是机器人，真正决定答案的是背后的引擎。
法师要的是「用 Qoder 客户端窗口回答」——那个窗口带工具、能看本机文件。
Qoder 客户端本身没有聊天接口，但它的无头工作进程可以（2026-11-06 实测）：

    ELECTRON_RUN_AS_NODE=1 "Qoder CN.exe" <worker-runtime.obf.mjs> \\
        --print --output-format stream-json --input-format stream-json \\
        --no-session-persistence

它从标准输入读 JSONL 的用户消息，把每一步事件按 JSONL 吐到标准输出。
本桥把它包成 OpenAI 兼容的 HTTP 服务，管家代理再把它当成一个池来用。

认证只有两条路（2026-11-06 实测）：
  · 个人访问令牌：环境变量 QODERCN_PERSONAL_ACCESS_TOKEN（载荷类型 accessToken）
  · 命令行登录态：先跑一次 qoderclicn login（载荷类型 qodercli，只读本机登录态）
个人访问令牌只从环境变量读，值不落盘、不进日志；打给工作进程时只在临时载荷文件里
短暂存在，子进程读完立刻删掉。

还有一条握手（2026-11-06 实测）：工作进程不是收到第一句话就答，它要求先来一条
control_request（subtype 为 initialize），收到成功的 control_response 之后，
后面发的用户消息才被受理。没握手就发问题，它回 initialize_required 并自己退出。
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import store

MODEL_ID = "qoder-window"
DEFAULT_PORT = 8792
WORKER_REL = Path("resources/app.asar.unpacked/node_modules/@qoder-ai/qoder-cn-agent-sdk/dist/_worker/qoder-worker-runtime.obf.mjs")
TOKEN_ENV_NAMES = ("QODERCN_PERSONAL_ACCESS_TOKEN", "QODER_PERSONAL_ACCESS_TOKEN")
DEFAULT_TOOLS = "Read,Glob,Grep"

# 用哪个模型：点名到「MiniMax-M3.1-Flash」（法师 2026-11-06 亲自点名要的那个）。
# 模型名取自 Qoder 客户端自己的清单（--list-models 的 MODEL 段），不是本地编的。
# 要改就设环境变量 AI_ROUTER_QODER_MODEL。
DEFAULT_MODEL = "MiniMax-M3.1-Flash"

# 只读工具：飞书群里能查看本机文件，但不能改本机文件。
DEFAULT_PERMISSION_MODE = "bypass_permissions"


def address() -> tuple[str, int]:
    raw = os.environ.get("AI_ROUTER_QODER_BRIDGE", "127.0.0.1:%d" % DEFAULT_PORT)
    host, _, port = raw.rpartition(":")
    try:
        return (host or "127.0.0.1"), int(port or DEFAULT_PORT)
    except ValueError:
        return "127.0.0.1", DEFAULT_PORT


def workspace_dir() -> Path:
    # parents[0]=ai_router、[1]=AI调用管家、[2]=01_项目管理、[3]=仓库根
    raw = os.environ.get("AI_ROUTER_QODER_WORKSPACE") or str(Path(__file__).resolve().parents[3])
    return Path(raw)


def _version_key(name: str) -> tuple:
    parts = re.findall(r"\d+", name)
    return tuple(int(p) for p in parts) or (0,)


def find_worker() -> tuple[Path, Path] | None:
    """找 Qoder 客户端的无头工作进程：取已装版本里最高的一个。"""
    root = Path.home() / "AppData" / "Local" / "Programs" / "Qoder CN" / ".qoder-versions"
    if not root.is_dir():
        return None
    versions = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: _version_key(p.name), reverse=True)
    for ver in versions:
        exe = ver / "Qoder CN.exe"
        mjs = ver / WORKER_REL
        if exe.exists() and mjs.exists():
            return exe, mjs
    return None


def read_token() -> str:
    """个人访问令牌：进程环境变量优先，用户级环境变量兜底。都不在就当没有。

    值只在内存里流转，不打印、不写进本项目任何文件。
    """
    for name in TOKEN_ENV_NAMES:
        value = (os.environ.get(name) or store.user_env(name) or "").strip()
        if value:
            return value
    return ""


def model_name() -> str:
    """工作进程用哪个模型。默认 Auto（客户端自己挑），环境变量可改。"""
    return (os.environ.get("AI_ROUTER_QODER_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _mask(text: str, token: str) -> str:
    if token and token in text:
        text = text.replace(token, "***")
    return text


def _first_problem(out: str) -> str:
    """从工作进程的输出里挑出那句人话。

    工作进程回的是一整行 JSON（errors / terminal_reason 在里面），面板要的是一句话，
    不是那坨 JSON。挑不出就退回首行。
    """
    for line in reversed(out.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        errors = data.get("errors") or []
        if errors:
            return str(errors[0])
        reason = data.get("terminal_reason")
        if reason:
            return str(reason)
    return next((ln.strip() for ln in out.splitlines() if ln.strip()), "没有输出")


class QoderWorker:
    """一个常驻的无头工作进程，当作一段会话用。

    进程不退出：多轮对话时上下文留着，群里接着问也能接上话。
    """

    def __init__(self, exe: Path, mjs: Path, cwd: Path, token: str) -> None:
        self.exe = exe
        self.mjs = mjs
        self.cwd = cwd
        self.token = token
        self.proc: subprocess.Popen | None = None
        self.events: queue.Queue = queue.Queue()
        self._payload_path: Path | None = None
        self._lock = threading.Lock()
        # 工作进程回话时自报的模型名（真名）。用来让外面看到的是真模型，
        # 而不是我们自己起的那个路由键。
        self.last_model = ""

    def start(self) -> None:
        payload = {"type": "accessToken", "accessToken": self.token} if self.token else {"type": "qodercli"}
        folder = Path(tempfile.mkdtemp(prefix="qoder-ai028-"))
        payload_file = folder / "payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")
        self._payload_path = payload_file
        env = dict(os.environ)
        env["ELECTRON_RUN_AS_NODE"] = "1"
        env["QODER_SDK_AUTH_PAYLOAD_FILE"] = str(payload_file)
        env.pop("QODER_AGENT_SDK_DAEMON", None)
        args = [
            str(self.exe), str(self.mjs),
            "--print", "--output-format", "stream-json", "--input-format", "stream-json",
            "--no-session-persistence",
            "--permission-mode", os.environ.get("AI_ROUTER_QODER_PERMISSION_MODE", DEFAULT_PERMISSION_MODE),
            # --tools 是变长参数，放末位，免得把后面的旗标吃进去。
            "--tools", os.environ.get("AI_ROUTER_QODER_TOOLS", DEFAULT_TOOLS),
        ]
        self.proc = subprocess.Popen(
            args, cwd=str(self.cwd), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        self._initialize()

    def _initialize(self, timeout: float = 90.0) -> None:
        """握手：先发一条 control_request（subtype=initialize），等它的成功回执。

        没这一步，工作进程收到用户消息会回 initialize_required 然后自己退出。
        """
        if self.proc is None:
            raise RuntimeError("工作进程没起来")
        request_id = "init-1"
        payload = {
            "type": "control_request",
            "request_id": request_id,
            "request": {"subtype": "initialize", "model": model_name()},
        }
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError("初始化握手超时")
            try:
                event = self.events.get(timeout=left)
            except queue.Empty:
                raise TimeoutError("初始化握手超时")
            kind = event.get("type")
            if kind == "control_response":
                body = event.get("response") or {}
                if body.get("request_id") != request_id:
                    continue
                if body.get("subtype") == "success":
                    return
                raise RuntimeError("初始化握手被拒：%s" % _mask(str(body.get("error") or "没给原因"), self.token))
            if kind == "result":
                raise RuntimeError("初始化就报错：%s" % _first_problem(json.dumps(event, ensure_ascii=False)))

    def _pump_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                self.events.put({"type": "_raw", "text": line})

    def _pump_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            line = line.strip()
            if line:
                self.events.put({"type": "_stderr", "text": line})

    def ask(self, prompt: str, timeout: float) -> tuple[str, dict]:
        """发一句话，等这一轮的 result 事件；返回（回答，用量）。"""
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError("工作进程没起来")
        payload = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}}
        with self._lock:
            assert self.proc.stdin
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            deadline = time.time() + timeout
            texts: list[str] = []
            final = ""
            usage: dict = {}
            while True:
                left = deadline - time.time()
                if left <= 0:
                    self._retire()
                    raise TimeoutError("等回答超时")
                try:
                    event = self.events.get(timeout=left)
                except queue.Empty:
                    self._retire()
                    raise TimeoutError("等回答超时")
                kind = event.get("type")
                if kind == "assistant":
                    for part in (event.get("message") or {}).get("content") or []:
                        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                            texts.append(part["text"])
                    # 助手事件里带 model 字段：那是工作进程真在用的模型名。
                    named = (event.get("message") or {}).get("model") or event.get("model")
                    if isinstance(named, str) and named.strip():
                        self.last_model = named.strip()
                elif kind == "result":
                    final = str(event.get("result") or "")
                    usage = event.get("usage") or {}
                    named = event.get("model") or (event.get("metadata") or {}).get("model")
                    if isinstance(named, str) and named.strip():
                        self.last_model = named.strip()
                    if event.get("is_error"):
                        raise RuntimeError(_mask(str(event.get("errors") or final or "工作进程报错"), self.token))
                    break
                elif kind == "_stderr":
                    text = _mask(str(event.get("text")), self.token)
                    if "Not logged in" in text or "login" in text.lower():
                        raise RuntimeError(text)
        return (final or "\n".join(texts)).strip(), usage

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self._drop_payload()

    def _retire(self) -> None:
        """这个工作进程已经哑了（超时且不再出声），杀掉它，下一轮换新的。

        不杀的话，worker_for 还会当它活着而复用，下一轮接着卡——实测过一轮挂死。
        """
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass

    def _drop_payload(self) -> None:
        if self._payload_path and self._payload_path.exists():
            try:
                self._payload_path.unlink()
            except OSError:
                pass


class Bridge:
    """桥的服务端：按会话键分配工作进程。"""

    def __init__(self) -> None:
        self.sessions: dict[str, QoderWorker] = {}
        self.lock = threading.Lock()
        self.ready = False
        self.reason = "还没探过"
        self.probed_at = 0.0

    def probe(self) -> tuple[bool, str]:
        """探身份：跑一次无头工作进程的「列模型」，只验登录，不花推理。

        旗标必须带全（--print/--input-format/--output-format）：工作进程缺一个就报
        sdk_invalid_args，那是启动参数错，不是登录错，别把两件事混成一个结论。
        """
        found = find_worker()
        if not found:
            self.ready = False
            self.reason = "没找到 Qoder 客户端"
            self.probed_at = time.time()
            return self.ready, self.reason
        exe, mjs = found
        token = read_token()
        payload = {"type": "accessToken", "accessToken": token} if token else {"type": "qodercli"}
        folder = Path(tempfile.mkdtemp(prefix="qoder-probe-"))
        payload_file = folder / "payload.json"
        payload_file.write_text(json.dumps(payload), encoding="utf-8")
        env = dict(os.environ)
        env["ELECTRON_RUN_AS_NODE"] = "1"
        env["QODER_SDK_AUTH_PAYLOAD_FILE"] = str(payload_file)
        try:
            proc = subprocess.run(
                [str(exe), str(mjs), "--print", "--input-format", "stream-json",
                 "--output-format", "stream-json", "--list-models"],
                cwd=str(workspace_dir()), env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=90,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            self.ready = False
            self.reason = "探身份失败：%s" % _mask(str(exc), token)
            self.probed_at = time.time()
            return self.ready, self.reason
        finally:
            try:
                payload_file.unlink()
            except OSError:
                pass
        out = (proc.stdout or "") + (proc.stderr or "")
        out = _mask(out, token)
        self.probed_at = time.time()
        if proc.returncode == 0 and out.strip():
            self.ready = True
            self.reason = "Qoder 客户端已登录"
            return self.ready, self.reason
        self.ready = False
        self.reason = _mask(_first_problem(out), token)
        return self.ready, self.reason

    def worker_for(self, key: str) -> QoderWorker:
        with self.lock:
            worker = self.sessions.get(key)
            if worker is not None and worker.proc is not None and worker.proc.poll() is None:
                return worker
            found = find_worker()
            if not found:
                raise RuntimeError("没找到 Qoder 客户端")
            exe, mjs = found
            worker = QoderWorker(exe, mjs, workspace_dir(), read_token())
            worker.start()
            self.sessions[key] = worker
            return worker

    def drop(self, key: str) -> None:
        with self.lock:
            worker = self.sessions.pop(key, None)
        if worker:
            worker.close()

    def close_all(self) -> None:
        with self.lock:
            workers = list(self.sessions.values())
            self.sessions.clear()
        for worker in workers:
            worker.close()


BRIDGE = Bridge()


def _session_key(payload: dict, headers) -> str:
    for name in ("x-opencode-session", "x-session-id"):
        value = (headers.get(name) or "").strip()
        if value:
            return value
    messages = payload.get("messages") or []
    if messages:
        head = json.dumps(messages[0], ensure_ascii=False, sort_keys=True)
        return "auto-" + str(abs(hash(head)))
    return "auto-default"


def _prompt_from(payload: dict) -> str:
    parts: list[str] = []
    for message in payload.get("messages") or []:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, list):
            text = "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        else:
            text = str(content or "")
        if not text.strip():
            continue
        if role == "system":
            parts.append("【系统要求】" + text.strip())
        elif role == "assistant":
            parts.append("【我上一轮说过】" + text.strip())
        else:
            parts.append(text.strip())
    return "\n\n".join(parts)


class Handler(BaseHTTPRequestHandler):
    server_version = "AIQoderBridge/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, key: str, answer: str, usage: dict, model: str = "") -> None:
        """流式回答：客户端要 stream=true 时，给它标准那套 SSE 块。

        少了最后那块带 finish_reason 的，客户端会判「流没结束」并重试（DSH 实测过）。
        """
        created = int(time.time())
        chat_id = "chatcmpl-" + key
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": usage.get("total_tokens") or (prompt_tokens + completion_tokens),
        }

        def block(delta: dict, finish: str | None = None, with_usage: bool = False) -> dict:
            body = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model or MODEL_ID,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            if with_usage:
                body["usage"] = token_usage
            return body

        blocks = [
            block({"role": "assistant", "content": ""}),
            block({"content": answer}),
            block({}, finish="stop", with_usage=True),
        ]
        text = "".join("data: %s\n\n" % json.dumps(item, ensure_ascii=False) for item in blocks)
        text += "data: [DONE]\n\n"
        raw = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/健康", "/health"):
            # 令牌是后设的，缓存的「没登录」会过期：过了半分钟还没就绪就重探一次。
            if not BRIDGE.ready and time.time() - BRIDGE.probed_at > 30:
                BRIDGE.probe()
            self._send(200, {"状态": "在跑", "就绪": BRIDGE.ready, "说明": BRIDGE.reason,
                             "工作区": str(workspace_dir()), "模型": model_name(),
                             "时刻": time.strftime("%Y-%m-%d %H:%M:%S")})
            return
        if path in ("/v1/models", "/models"):
            if not BRIDGE.ready:
                self._send(503, {"错误": "Qoder 客户端还没登录", "说明": BRIDGE.reason})
                return
            created = int(time.time())
            self._send(200, {"object": "list", "data": [
                {"id": MODEL_ID, "object": "model", "created": created, "owned_by": "qoder"}]})
            return
        self._send(404, {"错误": "没有这个路径"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/v1/chat/completions", "/v1/messages"):
            self._send(404, {"错误": "只接 /v1/chat/completions"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 16 * 1024 * 1024:
            self._send(400, {"错误": "请求体为空或过大"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"错误": "请求体不是合法 JSON"})
            return
        if not BRIDGE.ready:
            ok, why = BRIDGE.probe()
            if not ok:
                self._send(503, {"错误": "Qoder 客户端还没登录", "说明": why})
                return
        prompt = _prompt_from(payload)
        if not prompt.strip():
            self._send(400, {"错误": "没有内容可问"})
            return
        key = _session_key(payload, self.headers)
        timeout = float(os.environ.get("AI_ROUTER_QODER_TIMEOUT", "300"))
        try:
            worker = BRIDGE.worker_for(key)
            answer, usage = worker.ask(prompt, timeout)
        except Exception as exc:  # noqa: BLE001 - 失败原因要原样带给调用方
            self._send(502, {"错误": "Qoder 客户端没答上来", "说明": str(exc)})
            return
        # 回话里的模型名＝工作进程真在用的那个（MiniMax-M3.1-Flash 之类），
        # 不是路由键。这样 DSH 那边显示的、账本记的，都是真模型。
        real_model = getattr(worker, "last_model", "") or model_name()
        if payload.get("stream"):
            self._send_stream(key, answer, usage, real_model)
            return
        self._send(200, {
            "id": "chatcmpl-" + key,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": real_model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": answer}}],
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens")
                or (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
            },
        })


def serve(port: int | None = None) -> None:
    host, default_port = address()
    listen = port or default_port
    ok, why = BRIDGE.probe()
    server = ThreadingHTTPServer((host, listen), Handler)
    print("Qoder 客户端窗口桥：%s:%d  就绪=%s（%s）" % (host, listen, ok, why))
    print("工作区：%s" % workspace_dir())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        BRIDGE.close_all()
        server.server_close()


if __name__ == "__main__":
    serve()
