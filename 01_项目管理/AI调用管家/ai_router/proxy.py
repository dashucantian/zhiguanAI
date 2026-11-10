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

from ai_router import plans, pools, registry, router, store

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
OPENAI_RESPONSES_PATH = "/openai/v1/responses"
ANTHROPIC_PATH = "/anthropic/v1/messages"

# 每条入站路由对应的上游路径与客户端标识。Codex 打 responses 协议，
# 上游 Go 通道的 responses 端点本机 2026-11-05 实测 200，可直通。
ROUTES = {
    "/v1/chat/completions": (OPENAI_PATH, "openai-compatible"),
    "/v1/responses": (OPENAI_RESPONSES_PATH, "codex"),
    "/v1/messages": (ANTHROPIC_PATH, "claude-code"),
}

TASK_HEADER = "x-task-id"
WORKSPACE_HEADER = "x-ai-router-workspace"
CLIENT_HEADER = "x-ai-router-client"

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
    if not chunks and payload.get("input") is not None:
        # responses 协议（Codex 用）没有 messages，正文在 input 里。
        chunks.append(_flatten_text(payload.get("input")))
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


def _usage_from_stream(raw: bytes) -> dict:
    """流式响应里找用量：SSE 的最后一个带 usage 的事件，或 JSON 片段。"""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return {}
    best: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            usage = data.get("usage")
            if not isinstance(usage, dict):
                # responses 协议的流式事件把用量包在 response 里（如 response.completed）。
                usage = (data.get("response") or {}).get("usage")
            if isinstance(usage, dict):
                best = usage
    if best:
        return best
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = (data.get("response") or {}).get("usage")
    return usage if isinstance(usage, dict) else {}


def _price_and_cap(model: str, context_tokens: int) -> tuple[float, float | None]:
    price = plans.price_for(model, context_tokens)
    usd = plans.estimate_usd(model, context_tokens, output_tokens=2000)
    return usd, plans.cap_for(model)


def choose_model(requested: str, context_tokens: int) -> tuple[str, list[str]]:
    """定这次调用走哪个池、哪个模型。三个池都接不了就返回空串与理由。"""
    route = pools.choose(requested, context_tokens, task="批处理" if context_tokens > 120_000 else "改码")
    if route is None:
        return "", ["三个池都接不了：本地 Qwen 没服务、百炼缺密钥或没额度、Go 按月额度已用尽"]
    return route.upstream_model, route.notes


def user_env(name: str) -> str:
    """读用户级环境变量（Windows 走注册表）。键存在系统里，不落在本项目任何文件。"""
    return store.user_env(name)


def api_key() -> str:
    """上游密钥：进程环境变量优先，用户级环境变量兜底。都不在就当没有，代理退 503。

    值只在内存里流转，不打印、不写文件、不进日志。
    """
    return os.environ.get("OPENCODE_API_KEY") or user_env("OPENCODE_API_KEY")


def models_payload() -> dict:
    """给客户端看的模型清单，形态照 OpenAI 的 {"object":"list","data":[…]}。

    清单里的 id 全部取自 plans 的 Go 档封顶表，不另立一份——客户端拉到的名字必须是
    管家真能调的模型，否则拉到了清单却调不通。
    Qoder 客户端窗口那一条按桥的实际状态给：桥没起就不列，免得客户端拉到了却调不通。
    """
    created = int(time.time())
    ids = list(plans.model_ids())
    ready, _ = pools.qoder_bridge_state()
    if ready:
        ids.append("qoder-window")
    ids.sort()
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": created,
                "owned_by": "opencode",
            }
            for model in ids
        ],
    }


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

    def _drain(self, length: int) -> None:
        """把请求体读掉再回话。

        body 没读就回 404/401 并断连接，Windows 上客户端拿到的是
        「连接被中止」(10053)，看不到那个 404。
        """
        if length <= 0 or length > 32 * 1024 * 1024:
            return
        try:
            self.rfile.read(length)
        except OSError:
            pass

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/健康", "/health"):
            self._send(200, {"状态": "在跑", "时刻": time.strftime("%Y-%m-%d %H:%M:%S")})
            return
        if path in ("/v1/models", "/models"):
            # 清单里只有模型名与归属，不含任何凭据，所以这一路不设口令闸。
            self._send(200, models_payload())
            return
        self._send(404, {"错误": "没有这个路径"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0].rstrip("/")
        length = int(self.headers.get("Content-Length") or 0)
        if path not in ROUTES:
            self._drain(length)
            self._send(404, {"错误": "只接 /v1/chat/completions、/v1/responses 与 /v1/messages"})
            return
        token = os.environ.get("AI_ROUTER_TOKEN")
        if token:
            given = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if given != token and self.headers.get("x-api-key", "").strip() != token:
                self._drain(length)
                self._send(401, {"错误": "本机代理口令不对，请检查 AI_ROUTER_TOKEN 环境变量"})
                return
        if length <= 0 or length > 32 * 1024 * 1024:
            self._send(400, {"错误": "请求体为空或过大"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"错误": "请求体不是合法 JSON"})
            return

        task_id, workspace = resolve_task(self.headers)
        context_tokens = payload_context_tokens(payload)
        requested = str(payload.get("model") or "")
        route = pools.choose(requested, context_tokens,
                             task="批处理" if context_tokens > 120_000 else "改码")
        if route is None:
            self._refuse(task_id, self.headers.get(CLIENT_HEADER, "") or "-",
                         f"model={requested or 'auto'} 三个池都接不了：" + "；".join(pools.last_notes()))
            self._send(503, {"错误": "三个池都接不了这条调用",
                            "说明": "；".join(pools.last_notes())})
            return
        if path != "/v1/chat/completions" and route.pool != "opencode":
            self._refuse(task_id, self.headers.get(CLIENT_HEADER, "") or "-",
                         f"model={requested or 'auto'} 协议={path} 只有 OpenCode Go 支持")
            self._send(503, {"错误": f"{pools.pool_name(route.pool)}只支持 OpenAI 兼容的对话协议，这条协议只有 OpenCode Go 支持"})
            return

        model = route.upstream_model
        notes = route.notes
        if route.pool == "qoder-window":
            # 诊断：上游客户端（DSH 等）发来的请求形态要看得见，才知道它为何判定失败。
            notes.append("stream=%s tools=%d messages=%d" % (
                payload.get("stream"), len(payload.get("tools") or []),
                len(payload.get("messages") or [])))
        payload["model"] = model
        upstream_path, client = ROUTES[path]
        # 客户端可以自报名字（DSH 走 OpenAI 兼容协议，与 OpenCode 同一路，靠这个区分）。
        client = store.clean_task_id(self.headers.get(CLIENT_HEADER, "")) or client

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # Go 通道必须带 x-opencode-session，否则上游回 400 MissingSessionID。
        # 客户端带了就原样透传（保证同一会话命中同一份提示缓存），没带就按本次请求生成一个。
        session_id = self.headers.get("x-opencode-session", "").strip()
        if not session_id:
            session_id = f"ai-router-{uuid.uuid4().hex[:16]}"

        if route.pool == "opencode":
            upstream = GO_BASE + upstream_path
            headers = {
                "Authorization": f"Bearer {api_key()}",
                "Content-Type": "application/json",
                "x-opencode-session": session_id,
                # Go 上游前面有 Cloudflare，默认的 python-urllib UA 会被挡成 403 1010。
                "User-Agent": USER_AGENT,
            }
        else:
            upstream = route.base_url.rstrip("/") + "/chat/completions"
            headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
            key = store.env_value(pools.pool_key_name(route.pool))
            if key:
                headers["Authorization"] = f"Bearer {key}"
            if route.pool == "qoder-window":
                # 会话键透传给窗口桥：同一段对话接着问，窗口里上下文留着。
                headers["x-opencode-session"] = session_id

        request = urllib.request.Request(upstream, data=body, method="POST", headers=headers)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        started = time.time()
        # Qoder 客户端窗口要走工具、读文件，比普通对话慢，超时给宽。
        timeout = TIMEOUT
        if route.pool == "qoder-window":
            # 比桥自己的 300 秒宽一分钟：让桥先报「等回答超时」，代理再转述，
            # 免得代理先掐断，客户端只看到一个没头没尾的断线。
            timeout = float(os.environ.get("AI_ROUTER_QODER_TIMEOUT", "360"))
        content_type = "application/json; charset=utf-8"
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read()
                code = response.status
                content_type = response.headers.get("Content-Type") or content_type
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            code = exc.code
            content_type = exc.headers.get("Content-Type") or content_type
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            elapsed = int((time.time() - started) * 1000)
            audit({
                "task": task_id,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "channel": route.pool,
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
        self._record(route, raw, notes, upstream, code, elapsed, task_id, workspace, client)
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("x-ai-router-model", model)
        self.send_header("x-ai-router-pool", route.pool)
        if notes:
            self.send_header("x-ai-router-note", urllib.parse.quote("；".join(notes)[:300]))
        self.end_headers()
        self.wfile.write(raw)

    def _refuse(self, task_id: str, client: str, summary: str) -> None:
        """拒接的调用也要留痕：没花钱的账也要能查，否则事后看不出是谁在撞墙。"""
        audit({
            "task": task_id,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": "-",
            "action": "refuse",
            "http": "503",
            "summary": f"拒接 客户端={client} {summary}",
            "level": "L0_LOCAL",
            "approver": "-",
            "target": "-",
            "elapsed_ms": "-",
        })

    def _record(self, route: pools.Route, raw: bytes, notes: list[str], upstream: str, code: int, elapsed: int,
                task_id: str = "", workspace: str = "", client: str = "") -> None:
        model = route.upstream_model
        usage = {}
        try:
            data = json.loads(raw.decode("utf-8"))
            usage = data.get("usage") or (data.get("response") or {}).get("usage") or {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
            usage = _usage_from_stream(raw)
        if route.pool == "qoder-window":
            # 桥回话时带的是工作进程真在用的模型名（如 MiniMax-M3.1-Flash）。
            # 账本记这个真名，别只记「qoder-window」那个路由键——不然事后
            # 看账本只知道走了哪一路，不知道是哪个模型答的。
            real = str(data.get("model") or "").strip()
            if real:
                model = real
        prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens")
                     or (usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
        price = plans.price_for(model, max(prompt, 1))
        usd = round(
            (prompt * price["input"] + completion * price["output"] + cached * price["cache_read"]) / 1_000_000,
            6,
        )
        if route.pool != "opencode":
            # 非 Go 池没有按 token 的美元单价；记入口与调用次数，金额栏留 0。
            usd = 0.0
        billing = ""
        if route.pool == "opencode" and code != 200:
            # 上游没接住（403 地区限制、400 模型不可用等）：这一笔没花钱，不进账也不扣余额。
            usd = 0.0
        elif route.pool == "opencode":
            # 上游自己在 usage 里报实际扣了多少、扣的是哪一池（2026-11-05 实测）。
            # 以它为准，别拿本地估价当账。
            meta = usage.get("opencode") or {}
            source = str(meta.get("billing_source") or "")
            cost = usage.get("cost")
            if isinstance(cost, (int, float)) and cost > 0:
                usd = round(float(cost), 6)
            if source == "balance":
                billing = plans.GO_BALANCE_POOL
            elif source == "monthly":
                billing = plans.GO_PLAN_POOL
            else:
                billing = store.go_billing_mode() or plans.GO_PLAN_POOL
        if usd > 0 or route.pool != "opencode":
            store.append_ledger({
                "渠道": route.pool,
                "入口": route.entrance,
                "模型": model,
                "美元": usd,
                "次数": 1,
                "输入": prompt,
                "输出": completion,
                "缓存读": cached,
                "任务号": task_id or store.UNTAGGED,
                "工作区": workspace,
                "客户端": client,
                "计费来源": billing,
                "说明": "本机代理",
            })
        left = None
        if route.pool == "opencode" and usd > 0 and billing:
            # 把余额池的剩余扣掉：这是本地守住余额上限的那道闸，扣完才不会有人把 10 美元打光。
            left = store.consume_pool("opencode", billing, usd,
                                      note=f"本机代理按次扣减（{time.strftime('%Y-%m-%d %H:%M:%S')}）")
        audit({
            "task": task_id or store.UNTAGGED,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": route.pool,
            "action": "proxy",
            "http": str(code),
            "summary": f"model={model} pool={route.pool} in={prompt} out={completion} usd={usd}"
                       + (f" 计费={billing} 余额剩={left}" if billing else ""),
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
