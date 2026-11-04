"""本机代理：把编码客户端指向它，它按规则选模型、记账、卡预算。

只绑回环地址；上游密钥只从环境变量读，不落盘、不进日志。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if __package__ in (None, ""):
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from ai_router import plans, registry, router, store

DEFAULT_PORT = 8791
GO_BASE = os.environ.get("OPENCODE_GO_BASE", "https://opencode.ai/inference/go")
TIMEOUT = float(os.environ.get("AI_ROUTER_TIMEOUT", "120"))
USER_AGENT = os.environ.get(
    "AI_ROUTER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)
LOG_FILE = store.DATA_DIR / "审计.log"

OPENAI_PATH = "/openai/v1/chat/completions"
ANTHROPIC_PATH = "/anthropic/v1/messages"

TASK_HEADER = "x-task-id"
WORKSPACE_HEADER = "x-ai-router-workspace"

_CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return int(cjk + other / 4)


def _flatten_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return " ".join(parts)
    if isinstance(value, dict):
        return _flatten_text(value.get("text") or value.get("content") or "")
    return ""


def payload_context_tokens(payload: dict) -> int:
    chunks: list[str] = []
    system = payload.get("system")
    if system:
        chunks.append(_flatten_text(system))
    for message in payload.get("messages") or []:
        if isinstance(message, dict):
            chunks.append(_flatten_text(message.get("content")))
    if not chunks and payload.get("prompt"):
        chunks.append(str(payload["prompt"]))
    return estimate_tokens(" ".join(chunks))


def audit(fields: dict) -> None:
    order = ["task", "time", "channel", "action", "http", "summary", "level", "approver", "target", "elapsed_ms"]
    line = " ".join(f"{key}={fields.get(key, '-')}" for key in order)
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def resolve_task(headers) -> tuple[str, str]:
    """任务号从哪来：客户端带的头 → 本机「当前任务」设定 → 代理环境变量 → 未标记。

    都不猜：没有来源就写「未标记」，事后能看出哪些调用没挂上任务。
    """
    task = store.clean_task_id(headers.get(TASK_HEADER, ""))
    workspace = store.clean_workspace(headers.get(WORKSPACE_HEADER, ""))
    if not task:
        current = store.get_current_task()
        task = store.clean_task_id(current.get("任务号", ""))
        workspace = workspace or store.clean_workspace(current.get("工作区", ""))
    if not task:
        task = store.clean_task_id(os.environ.get("AI_ROUTER_TASK_ID", ""))
    task = task or store.UNTAGGED
    if not workspace:
        workspace = _worktree_workspace(task)
    return task, workspace


def _worktree_workspace(task_id: str) -> str:
    """工作区栏接真值：这个任务号对应的隔离树若在盘，就把它的路径填上。

    填的是实测存在的路径，不接受人随手写的字符串——工作区栏要能当「执行位置」用。
    """
    return registry.expected_workspace(task_id)


def _price_and_cap(model: str, context_tokens: int) -> tuple[float, float | None]:
    price = plans.price_for(model, context_tokens)
    usd = plans.estimate_usd(model, context_tokens, output_tokens=2000)
    return usd, plans.cap_for(model)


def choose_model(requested: str, context_tokens: int) -> tuple[str, list[str]]:
    notes: list[str] = []
    known = requested and requested not in ("auto", "管家", "auto-router")
    if known:
        cap = plans.cap_for(requested)
        used = store.spend_by_model().get(requested, 0.0)
        if cap and used / cap >= router.SOFT_STOP:
            notes.append(f"{requested} 本月已用 {used:.2f} 美元、封顶 {cap:.0f} 美元，改走免费模型")
            return plans.FREE_FALLBACK[0], notes
        notes.append(f"按你指定的模型走：{requested}")
        return requested, notes
    model, reasons = router.pick_model("批处理" if context_tokens > 120_000 else "改码", context_tokens)
    notes.extend(reasons)
    if model is None:
        model = plans.FREE_FALLBACK[0]
    return model, notes


class Handler(BaseHTTPRequestHandler):
    server_version = "AIRouter/1.0"

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def _send(self, code: int, payload: dict, extra: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/健康", "/health"):
            self._send(200, {"状态": "在跑", "时刻": time.strftime("%Y-%m-%d %H:%M:%S")})
            return
        self._send(404, {"错误": "没有这个路径"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path not in ("/v1/chat/completions", "/v1/messages"):
            self._send(404, {"错误": "只接 /v1/chat/completions 与 /v1/messages"})
            return
        token = os.environ.get("AI_ROUTER_TOKEN")
        if token:
            given = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if given != token and self.headers.get("x-api-key", "").strip() != token:
                self._send(401, {"错误": "本机代理口令不对，请检查 AI_ROUTER_TOKEN 环境变量"})
                return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 32 * 1024 * 1024:
            self._send(400, {"错误": "请求体为空或过大"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"错误": "请求体不是合法 JSON"})
            return

        api_key = os.environ.get("OPENCODE_API_KEY")
        if not api_key:
            self._send(503, {"错误": "没有 OPENCODE_API_KEY 环境变量，代理不代你取密钥。"})
            return

        task_id, workspace = resolve_task(self.headers)
        context_tokens = payload_context_tokens(payload)
        requested = str(payload.get("model") or "")
        model, notes = choose_model(requested, context_tokens)
        payload["model"] = model
        if path == "/v1/messages":
            upstream = GO_BASE + ANTHROPIC_PATH
        else:
            upstream = GO_BASE + OPENAI_PATH

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # Go 通道必须带 x-opencode-session，否则上游回 400 MissingSessionID。
        # 客户端带了就原样透传（保证同一会话命中同一份提示缓存），没带就按本次请求生成一个。
        session_id = self.headers.get("x-opencode-session", "").strip()
        if not session_id:
            session_id = f"ai-router-{uuid.uuid4().hex[:16]}"
        request = urllib.request.Request(
            upstream,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "x-opencode-session": session_id,
                # Go 上游前面有 Cloudflare，默认的 python-urllib UA 会被挡成 403 1010。
                "User-Agent": USER_AGENT,
            },
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        started = time.time()
        try:
            with opener.open(request, timeout=TIMEOUT) as response:
                raw = response.read()
                code = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            code = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            elapsed = int((time.time() - started) * 1000)
            audit({
                "task": task_id,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "channel": "opencode",
                "action": "proxy",
                "http": "000",
                "summary": f"上游失败 {exc}",
                "level": "L3_EGRESS",
                "approver": "-",
                "target": upstream,
                "elapsed_ms": elapsed,
            })
            self._send(502, {"错误": f"上游没打通：{exc}"})
            return

        elapsed = int((time.time() - started) * 1000)
        self._record(model, raw, notes, upstream, code, elapsed, task_id, workspace)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("x-ai-router-model", model)
        if notes:
            self.send_header("x-ai-router-note", urllib.parse.quote("；".join(notes)[:300]))
        self.end_headers()
        self.wfile.write(raw)

    def _record(self, model: str, raw: bytes, notes: list[str], upstream: str, code: int, elapsed: int,
                task_id: str = "", workspace: str = "") -> None:
        usage = {}
        try:
            data = json.loads(raw.decode("utf-8"))
            usage = data.get("usage") or {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        price = plans.price_for(model, max(prompt, 1))
        usd = round(
            (prompt * price["input"] + completion * price["output"] + cached * price["cache_read"]) / 1_000_000,
            6,
        )
        if usd > 0:
            store.append_ledger({
                "渠道": "opencode",
                "模型": model,
                "美元": usd,
                "次数": 1,
                "输入": prompt,
                "输出": completion,
                "缓存读": cached,
                "任务号": task_id or store.UNTAGGED,
                "工作区": workspace,
                "说明": "本机代理",
            })
        audit({
            "task": task_id or store.UNTAGGED,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": "opencode",
            "action": "proxy",
            "http": str(code),
            "summary": f"model={model} in={prompt} out={completion} usd={usd}",
            "level": "L0_LOCAL" if "127.0.0.1" in upstream or "localhost" in upstream else "L3_EGRESS",
            "approver": "-",
            "target": upstream,
            "elapsed_ms": elapsed,
        })


def serve(port: int | None = None) -> None:
    port = port or int(os.environ.get("AI_ROUTER_PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"本机代理已在 http://127.0.0.1:{port} 上开起来，回车或 Ctrl+C 结束。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="止观AI 本机自动分流代理")
    parser.add_argument("--端口", dest="port", type=int, default=None)
    args = parser.parse_args()
    serve(args.port)
