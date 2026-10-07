"""止观AI 可视化任务看板 · 服务端 v0.1

启动：python board_server.py   （或双击 启动任务看板.bat）
默认 http://127.0.0.1:8848 —— 只听本机回环，不对外网开放。

边界（写死在代码里，不是口号）：
- 只读外部数据：Qoder 会话元数据、维那看板快照、系统资源。不改任何他窗文件。
- 密钥只从环境变量读，永不返回前端、永不写盘、永不入模型上下文。
- 「加速／暂停／优先级」对看板自有作业队列真实生效；对 AI 窗口只能生成投递单（需法师粘贴或授权），不伪造控制权。
"""
from __future__ import annotations

import base64
import heapq
import json
import os
import threading
import time
import uuid
from pathlib import Path

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import board_privacy as priv
import board_sources as src

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
STATE = HERE / "state"
SCREEN_DIR = STATE / "screen"
STATE.mkdir(exist_ok=True)
SCREEN_DIR.mkdir(exist_ok=True)

HOST = os.environ.get("BOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("BOARD_PORT", "8848"))

app = FastAPI(title="止观AI 可视化任务看板", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

CACHE: dict[str, dict] = {"sessions": {}, "resources": {}, "backlog": {}}
CACHE_LOCK = threading.Lock()


# ─────────────────────────── 作业队列 ───────────────────────────

class Job:
    def __init__(self, job_id, name, fn, interval=0.0, priority=50, kind="auto", note=""):
        self.id = job_id
        self.name = name
        self.fn = fn
        self.interval = interval
        self.priority = priority
        self.kind = kind
        self.note = note
        self.paused = False
        self.state = "idle"
        self.runs = 0
        self.errors = 0
        self.lastRunAt = 0
        self.lastDurMs = 0
        self.lastError = ""
        self.nextRunAt = time.time() + 1.0 if interval else 0
        self.lastResult = ""

    def public(self):
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "note": self.note,
            "priority": self.priority, "paused": self.paused, "state": self.state,
            "interval": self.interval, "runs": self.runs, "errors": self.errors,
            "lastRunAt": int(self.lastRunAt * 1000), "lastDurMs": self.lastDurMs,
            "nextRunAt": int(self.nextRunAt * 1000) if self.nextRunAt else 0,
            "lastError": self.lastError, "lastResult": self.lastResult,
        }


class JobQueue:
    """优先级队列：priority 小者先跑；暂停的作业不入队；interval 作业到点重排。"""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.heap: list[tuple] = []
        self.seq = 0
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.alive = True

    def add(self, job: Job):
        self.jobs[job.id] = job
        if job.interval and not job.paused:
            self.push(job)

    def push(self, job: Job):
        with self.lock:
            self.seq += 1
            # 到期时间优先、优先级只作同时到期时的排序键——否则高频高优作业会把低频作业饿死（实测缺陷）
            heapq.heappush(self.heap, (job.nextRunAt or time.time(), job.priority, self.seq, job.id))
        self.wake.set()

    def _reschedule(self, job: Job):
        if job.interval and not job.paused and self.alive:
            job.nextRunAt = time.time() + job.interval
            self.push(job)

    def run_one(self, job: Job):
        job.state = "running"
        t0 = time.perf_counter()
        try:
            result = job.fn()
            job.lastResult = str(result or "")[:200]
            job.lastError = ""
            job.runs += 1
        except Exception as exc:
            job.lastError = f"{type(exc).__name__}: {exc}"[:300]
            job.errors += 1
        job.lastDurMs = round((time.perf_counter() - t0) * 1000, 1)
        job.lastRunAt = time.time()
        job.state = "paused" if job.paused else "idle"
        self._reschedule(job)

    def loop(self):
        while self.alive:
            with self.lock:
                peek = self.heap[0] if self.heap else None
            if peek is None:
                self.wake.wait(0.5)
                self.wake.clear()
                continue
            due, _, _, job_id = peek
            now = time.time()
            if due > now:
                self.wake.wait(min(due - now, 0.5))
                self.wake.clear()
                continue
            with self.lock:
                heapq.heappop(self.heap)
            job = self.jobs.get(job_id)
            if job is None or job.paused:
                continue
            self.run_one(job)


QUEUE = JobQueue()


def _cache_put(key, value):
    with CACHE_LOCK:
        CACHE[key] = value
    return value


def job_resources():
    data = src.resources()
    _cache_put("resources", data)
    return f"CPU {data['cpuPercent']}% · 内存 {data['memPercent']}%"


def job_sessions():
    data = src.scan_sessions()
    _cache_put("sessions", data)
    return f"{len(data.get('windows', []))} 窗"


def job_backlog():
    data = src.backlog()
    _cache_put("backlog", data)
    return f"{data.get('total') or 0} 行" if data.get("ok") else data.get("reason", "失败")


def job_model_probe():
    out = []
    for m in src.models_registry()["models"]:
        if m["kind"] != "chat":
            continue
        r = probe_model(m["id"])
        out.append(f"{m['id']}={'通' if r.get('ok') else '断'}")
    return "、".join(out)


QUEUE.add(Job("resources", "系统资源采样", job_resources, interval=5, priority=10,
              note="CPU／内存／磁盘／网络／进程 Top"))
QUEUE.add(Job("sessions", "Qoder 会话与任务扫描", job_sessions, interval=20, priority=20,
              note="只读 jsonl 尾部元数据＋tasks/*.json，不读对话正文"))
QUEUE.add(Job("backlog", "维那看板快照读取", job_backlog, interval=300, priority=30,
              note="读最新 _records_raw.json；真正拉取需 AI 窗口跑 20261007_W3_维那快照拉取_v1.py"))
QUEUE.add(Job("model_probe", "模型探活（全部）", job_model_probe, priority=40, kind="manual",
              note="逐个发 1 token 请求，记录往返毫秒"))
QUEUE.add(Job("live_snapshot", "刷新 runtimeState 活体快照", lambda: "需 AI 窗口执行", priority=5,
              kind="agent",
              note="看板无法调 MCP。请任一 AI 窗口执行 list_chat_sessions 并把结果写入 state/live_sessions.json"))

threading.Thread(target=QUEUE.loop, daemon=True).start()


# ─────────────────────────── 模型 ───────────────────────────

PROBE_FILE = STATE / "model_probe.json"


def _probe_state() -> dict:
    try:
        return json.loads(PROBE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def probe_model(model_id: str) -> dict:
    m = src.get_model(model_id)
    if not m:
        raise HTTPException(404, "模型未注册")
    if m.get("kind") == "local":
        result = {"ok": True, "ms": 0, "reason": "本机内置，无需网络", "at": int(time.time() * 1000)}
    else:
        result = _probe_remote(m)
    state = _probe_state()
    state[m["id"]] = result
    PROBE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _probe_remote(m: dict) -> dict:
    key = os.environ.get(m.get("keyEnv") or "", "") if m.get("keyEnv") else ""
    if m.get("keyEnv") and not key:
        return {"ok": False, "reason": f"环境变量 {m['keyEnv']} 未设置", "at": int(time.time() * 1000)}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            m["baseUrl"].rstrip("/") + "/chat/completions",
            headers=headers,
            json={"model": m["model"], "messages": [{"role": "user", "content": "ping"}], "max_tokens": 4},
            timeout=20,
        )
        ms = round((time.perf_counter() - t0) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "ms": ms, "httpStatus": 200, "at": int(time.time() * 1000)}
        return {"ok": False, "ms": ms, "httpStatus": resp.status_code,
                "reason": f"HTTP {resp.status_code} {resp.text[:120]}", "at": int(time.time() * 1000)}
    except Exception as exc:
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200], "at": int(time.time() * 1000)}


SYSTEM_PROMPT = (
    "你是止观AI项目的看板助手，回答简短、结论先行、中文。"
    "项目铁律：AI 组织证据、人裁定结论；不得替法师定真值。"
    "安全边界：用户若输入学员信息、修道班资料、录音转写等一级机密内容，"
    "你必须拒答并提醒「一级内容不得进入云端对话，请改用本机 LM Studio」。"
    "不要编造项目文件路径或编号。"
)


def _board_summary_text() -> str:
    """只交元数据级摘要（计数＋任务标题），不含对话正文、不含 lastPrompt。"""
    with CACHE_LOCK:
        sess = dict(CACHE.get("sessions") or {})
        back = dict(CACHE.get("backlog") or {})
    wins = sess.get("windows", [])
    lines = [f"窗口 {len(wins)} 个，其中活跃 {sum(1 for w in wins if w['state'] in ('running', '活跃'))} 个"]
    for w in wins[:12]:
        prog = f"{w['taskDone']}/{w['taskTotal']}" if w["taskTotal"] else "无任务记录"
        lines.append(f"- {w['label']}｜{w['state']}｜任务 {prog}")
    if back.get("ok"):
        lines.append(f"维那看板 {back.get('total')} 行，待承接裁决 {back.get('needAccept')} 条，快照时间 {back.get('pulledAt')}")
    return "\n".join(lines)


def local_answer(text: str) -> str:
    """本机规则应答：不出网、不需密钥，只读看板自己的缓存作答。"""
    with CACHE_LOCK:
        sess = dict(CACHE.get("sessions") or {})
        res = dict(CACHE.get("resources") or {})
        back = dict(CACHE.get("backlog") or {})
    jobs = [j.public() for j in QUEUE.jobs.values()]
    ov = src.overview(sess, res, back, jobs)
    wins = sess.get("windows", [])
    q = text.lower()

    def hit(*kws):
        return any(k in text or k in q for k in kws)

    if hit("窗口", "在跑", "几个", "运行", "window"):
        run = [w for w in wins if w["state"] in ("running", "活跃")]
        out = [f"扫到 {len(wins)} 个窗口，其中活跃 {len(run)} 个（其余静默）。",
               f"状态来源：{'MCP 活体快照' if sess.get('snapshot', {}).get('fresh') else '磁盘 mtime 推断（活体快照过期）'}"]
        for w in run[:6]:
            out.append(f"· 活跃：{w['label']}｜{w['state']}｜任务 {w['taskDone']}/{w['taskTotal']}")
        for w in wins[:6]:
            if w not in run:
                # 照实报 MCP 给的态（cold／静默／未知），不得一律改口成「静默」
                out.append(f"· {w['state']}：{w['label']}｜{time.strftime('%m-%d %H:%M', time.localtime(w['updatedAt'] / 1000))}")
        return "\n".join(out)

    if hit("任务", "进度", "todo"):
        out = [f"各窗任务共 {ov['taskTotal']} 项：已完成 {ov['taskDone']}、进行中 {ov['taskInProgress']}、待办 {ov['taskPending']}。"]
        for w in wins:
            if w["taskTotal"]:
                out.append(f"· {w['label']}：{w['taskDone']}/{w['taskTotal']}（{w['progress']}%）")
        return "\n".join(out)

    if hit("积压", "维那", "裁决", "承接", "看板"):
        if not back.get("ok"):
            return "维那快照还没读到：" + str(back.get("reason", "缓存为空"))
        out = [f"维那看板 {back.get('total')} 行，快照时间 {back.get('pulledAt')}。",
               f"待承接裁决（含【裁决】且受理戳为空）：{back.get('needAccept')} 条。"]
        for k, v in sorted((back.get("byStatus") or {}).items(), key=lambda x: -x[1]):
            out.append(f"· {k}：{v}")
        for r in (back.get("needAcceptRows") or [])[:5]:
            out.append(f"! {r.get('code') or '—'} {r.get('name')}")
        return "\n".join(out)

    if hit("资源", "cpu", "内存", "磁盘", "占用"):
        return "\n".join([
            f"CPU {ov.get('cpuPercent')}%（{res.get('cpuCores')} 核）｜内存 {ov.get('memPercent')}%（{res.get('memUsedGB')}/{res.get('memTotalGB')} GB）",
            *[f"· {d['mount']} 盘 {d['percent']}%（{d['usedGB']}/{d['totalGB']} GB）" for d in res.get("disks", [])],
            f"· 进程：python {res.get('pyProcs')} 个、node {res.get('nodeProcs')} 个",
            f"· 网络：↑{res.get('netUpKBs', '—')} ↓{res.get('netDownKBs', '—')} KB/s",
        ])

    if hit("作业", "队列", "暂停", "优先级"):
        out = [f"看板作业 {len(jobs)} 个：暂停 {ov['jobPaused']}、运行中 {ov['jobRunning']}。"]
        for j in sorted(jobs, key=lambda x: x["priority"]):
            flag = "已暂停" if j["paused"] else j["state"]
            out.append(f"· [{j['priority']}] {j['name']}｜{flag}｜跑 {j['runs']} 次｜{j['lastDurMs']}ms"
                       + (f"｜错 {j['lastError'][:40]}" if j["lastError"] else ""))
        return "\n".join(out)

    if hit("模型", "密钥", "千问", "qwen", "lm studio"):
        reg = src.models_registry()
        out = ["模型接入现状："]
        for m in reg["models"]:
            p = m.get("lastProbe") or {}
            st = ("通 " + str(p.get("ms")) + "ms") if p.get("ok") else (p.get("reason") or "未探活")
            out.append(f"· {m['label']}｜{m['egress']}｜密钥{'就位' if m['keyPresent'] else ('不需要' if not m['keyEnv'] else '缺')}｜{st}")
        out.append("提示：探活按「全部探活」即实测，不看名义值。")
        return "\n".join(out)

    return "\n".join([
        f"本机规则应答（不出网）。当前：窗口 {ov['windowRunning']}/{ov['windowTotal']} 活跃，"
        f"任务 {ov['taskDone']}/{ov['taskTotal']} 完成，积压 {ov['backlogTotal']} 行，CPU {ov['cpuPercent']}%。",
        "可问：几个窗口在跑／任务进度／积压与裁决／资源占用／作业队列／模型密钥。",
        "开放性问题请切到千问或 LM Studio——本机规则应答不是大模型。",
    ])


def _screen_payload(name: str, model: dict) -> tuple[dict | None, str]:
    """闸4 出网判定（图像）：只接受脱敏产物，其它文件名一律拒。

    返回 (image_part, error)；error 非空即不发。
    """
    if not name:
        return None, ""
    p = (SCREEN_DIR / name).resolve()
    if p.parent != SCREEN_DIR.resolve() or not p.is_file():
        return None, "闸4 拦截：找不到该图（只接受 state/screen/ 内的脱敏产物）"
    if ".masked." not in p.name:
        return None, priv.guard_image_outbound(False, model)["reason"]
    g = priv.guard_image_outbound(True, model)
    if not g["allowed"]:
        return None, g["reason"]
    b64 = base64.b64encode(p.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}, ""


def chat_stream(text: str, model_id: str | None, include_summary: bool, screen_file: str | None = None):
    m = src.get_model(model_id)
    if not m:
        yield _sse({"error": "模型未注册"})
        return
    if m.get("kind") == "local":
        priv.guard_outbound(text, m)          # 本机路径也过闸，只计数不拦
        if screen_file:
            priv.guard_image_outbound(".masked." in screen_file, m)
        yield _sse({"model": m["id"], "label": m["label"]})
        if screen_file:
            yield _sse({"notice": "本机规则应答不看图（它不是大模型）。要看图请切 LM Studio 或云端模型。"})
        answer = local_answer(text)
        for i in range(0, len(answer), 24):
            yield _sse({"delta": answer[i:i + 24]})
            time.sleep(0.012)
        yield _sse({"done": True})
        return

    # ── 闸2／闸3／闸4：外发前强制过隐私闸门（服务端，绕过前端也拦得住）──
    gate = priv.guard_outbound(text, m)
    if not gate["allowed"]:
        yield _sse({"blocked": True, "error": gate["reason"]})
        return
    if gate.get("hits"):
        yield _sse({"notice": gate.get("note", "")})
    outbound = gate["text"]

    parts = []
    if screen_file:
        img_part, err = _screen_payload(screen_file, m)
        if err:
            yield _sse({"blocked": True, "error": err})
            return
        parts.append(img_part)
        yield _sse({"notice": "已附闸4 脱敏图（未打码原图不出网）。" + priv.POLICY["residual"]})

    key = os.environ.get(m.get("keyEnv") or "", "") if m.get("keyEnv") else ""
    if m.get("keyEnv") and not key:
        yield _sse({"error": f"环境变量 {m['keyEnv']} 未设置——请先跑 设置千问密钥.ps1"})
        return
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if include_summary:
        summary = _board_summary_text()
        sg = priv.guard_outbound(summary, m)
        if sg["allowed"]:
            messages.append({"role": "system", "content": "以下是看板本地元数据摘要（仅计数与任务标题）：\n" + sg["text"]})
        else:
            yield _sse({"notice": "看板摘要含一级关键词，已按闸2 整段不外发"})
    if parts:
        parts.insert(0, {"type": "text", "text": outbound})
        messages.append({"role": "user", "content": parts})
    else:
        messages.append({"role": "user", "content": outbound})
    try:
        resp = requests.post(
            m["baseUrl"].rstrip("/") + "/chat/completions",
            headers=headers,
            json={"model": m["model"], "messages": messages, "stream": True},
            stream=True, timeout=90,
        )
    except Exception as exc:
        yield _sse({"error": f"请求失败：{type(exc).__name__}: {exc}"})
        return
    if resp.status_code != 200:
        yield _sse({"error": f"HTTP {resp.status_code}：{resp.text[:200]}"})
        return
    yield _sse({"model": m["id"], "label": m["label"]})
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        payload = raw[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
        if delta:
            yield _sse({"delta": delta})
    yield _sse({"done": True})


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ─────────────────────────── 路由 ───────────────────────────

class ChatReq(BaseModel):
    text: str
    modelId: str | None = None
    includeSummary: bool = False
    screenFile: str | None = None    # 只接受闸4 产出的 *.masked.png，原名一律拒


class JobReq(BaseModel):
    action: str
    value: int | None = None


class DispatchReq(BaseModel):
    sessionId: str
    action: str = "加速"
    note: str = ""


class ScreenReq(BaseModel):
    modelId: str | None = None


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


@app.get("/api/overview")
def api_overview():
    with CACHE_LOCK:
        sess = CACHE.get("sessions")
        res = CACHE.get("resources")
        back = CACHE.get("backlog")
    if not sess:
        sess = _cache_put("sessions", src.scan_sessions())
    if not res:
        res = _cache_put("resources", src.resources())
    if not back:
        back = _cache_put("backlog", src.backlog())
    jobs = [j.public() for j in QUEUE.jobs.values()]
    return src.overview(sess, res, back, jobs)


@app.get("/api/windows")
def api_windows():
    with CACHE_LOCK:
        data = CACHE.get("sessions")
    if data:
        return data
    return _cache_put("sessions", src.scan_sessions())


@app.get("/api/resources")
def api_resources():
    with CACHE_LOCK:
        data = CACHE.get("resources")
    return data or _cache_put("resources", src.resources())


@app.get("/api/backlog")
def api_backlog():
    with CACHE_LOCK:
        data = CACHE.get("backlog")
    return data or _cache_put("backlog", src.backlog())


@app.get("/api/jobs")
def api_jobs():
    return {"jobs": [j.public() for j in QUEUE.jobs.values()]}


@app.post("/api/jobs/{job_id}/control")
def api_job_control(job_id: str, req: JobReq):
    job = QUEUE.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "作业不存在")
    if req.action == "pause":
        job.paused = True
        job.state = "paused"
    elif req.action == "resume":
        job.paused = False
        job.state = "idle"
        if job.interval:
            job.nextRunAt = time.time() + 0.5
            QUEUE.push(job)
    elif req.action == "priority":
        if req.value is None or not (1 <= req.value <= 99):
            raise HTTPException(400, "优先级须为 1–99")
        job.priority = req.value
        if job.interval and not job.paused:
            QUEUE.push(job)
    elif req.action == "run":
        if job.kind == "agent":
            return {"ok": False, "reason": job.note}
        job.nextRunAt = time.time()
        QUEUE.push(job)
    else:
        raise HTTPException(400, "未知动作")
    return {"ok": True, "job": job.public()}


@app.get("/api/models")
def api_models():
    return src.models_registry()


@app.post("/api/models/{model_id}/probe")
def api_probe(model_id: str):
    return probe_model(model_id)


@app.post("/api/chat")
def api_chat(req: ChatReq):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "空消息")
    if len(text) > 4000:
        raise HTTPException(400, "单条消息过长（>4000 字）")
    from starlette.concurrency import iterate_in_threadpool

    gen = chat_stream(text, req.modelId, req.includeSummary, req.screenFile)
    return StreamingResponse(iterate_in_threadpool(gen), media_type="text/event-stream")


@app.post("/api/dispatch")
def api_dispatch(req: DispatchReq):
    """生成投递单文本——看板不代发消息（跨窗投递须法师授权）。"""
    with CACHE_LOCK:
        sess = CACHE.get("sessions") or {}
    win = next((w for w in sess.get("windows", []) if w["sessionId"] == req.sessionId), None)
    if win is None:
        raise HTTPException(404, "会话不在扫描范围")
    verb = {"加速": "请即刻推进并回报", "暂停": "请停手候裁，不再推进", "优先级": "请调整优先级"}.get(req.action, req.action)
    text = "\n".join([
        f"【法师投递·{req.action}】目标窗口：{win['label']}（sessionId {win['sessionId'][:8]}）",
        f"当前状态：{win['state']}｜任务 {win['taskDone']}/{win['taskTotal']}",
        f"要求：{verb}。",
        f"补充：{req.note or '（无）'}",
        "",
        "硬口径：只 add 本窗显式路径；禁 git add .／commit -a／push／amend；",
        "committer 不得落法师账号；改前先 git status 查他窗在途变更，见非己产生的变更即停下报告。",
        f"回执落本窗己档：01_项目管理\\信箱\\engine\\巡检日志-{win.get('window') or 'W?'}.txt",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
    ])
    return {"ok": True, "text": text, "note": "看板不代发。请法师粘贴到目标窗口，或明示授权由某一窗经 MCP 投递。"}


@app.get("/api/privacy")
def api_privacy():
    reg = src.models_registry()
    return {
        "policy": priv.POLICY,
        "counters": priv.counters(),
        "models": [{"id": m["id"], "label": m["label"], "egress": m["egress"],
                    "local": priv.is_local(m)} for m in reg["models"]],
        "tier1Keywords": priv.TIER1_KEYWORDS,
    }


@app.post("/api/screen/capture")
def api_screen_capture(req: ScreenReq | None = None):
    """屏幕共享——本机实现。截图只落 state/screen/（已全目录 gitignore），只经回环显示。"""
    model = src.get_model(req.modelId) if (req and req.modelId) else None
    gate = priv.guard_screen(model)
    if not gate["allowed"]:
        return JSONResponse({"ok": False, "reason": gate["reason"], "scope": gate["scope"]}, status_code=403)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        return JSONResponse({"ok": False, "reason": f"截屏失败：{type(exc).__name__}: {exc}"}, status_code=500)
    name = f"shot-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.png"
    path = SCREEN_DIR / name
    img.save(path, "PNG")
    priv._bump("screenCaptured")
    return {"ok": True, "file": name, "sizeKB": round(path.stat().st_size / 1024),
            "width": img.width, "height": img.height, "scope": gate["scope"],
            "note": gate["note"] + "｜不入库、不出网、不送云端模型", "at": int(time.time() * 1000)}


@app.get("/api/screen/list")
def api_screen_list():
    rows = []
    for p in sorted(SCREEN_DIR.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        rows.append({"file": p.name, "sizeKB": round(st.st_size / 1024), "at": int(st.st_mtime * 1000)})
    return {"count": len(rows), "shots": rows[:20],
            "note": "全部只存本机 state/screen/，该目录已整目录 gitignore；清理请显式指名文件，禁 glob"}


@app.get("/api/screen/latest")
def api_screen_latest():
    shots = [p for p in sorted(SCREEN_DIR.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)
             if ".masked." not in p.name]
    if not shots:
        raise HTTPException(404, "尚未截屏")
    return FileResponse(str(shots[0]), media_type="image/png")


@app.post("/api/screen/redact")
def api_screen_redact():
    """闸4 脱敏：本机截屏 → 本机 OCR 定位敏感行 → 整行实心遮盖 → 另存打码图。

    未打码原图留在本机且永不出网；本端点只产出"可以送"的那一张。
    """
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        return JSONResponse({"ok": False, "reason": f"截屏失败：{type(exc).__name__}: {exc}"}, status_code=500)
    name = f"shot-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.png"
    raw = SCREEN_DIR / name
    img.save(raw, "PNG")
    priv._bump("screenCaptured")

    out = priv.redact_image(raw, SCREEN_DIR)
    if not out["allowed"]:
        return JSONResponse({"ok": False, "reason": out["reason"], "rawFile": name,
                             "residual": priv.POLICY["residual"]}, status_code=403)
    return {"ok": True, "rawFile": name, "maskedFile": out["maskedName"],
            "hitLines": out["hitLines"], "maskedWords": out["maskedWords"],
            "categories": out["categories"], "ocrLines": out["ocrLines"], "engine": out["engine"],
            "note": out["note"], "residual": priv.POLICY["residual"],
            "width": img.width, "height": img.height, "at": int(time.time() * 1000)}


@app.get("/api/screen/masked")
def api_screen_masked():
    shots = sorted(SCREEN_DIR.glob("*.masked.png"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not shots:
        raise HTTPException(404, "尚未做脱敏")
    return FileResponse(str(shots[0]), media_type="image/png")


@app.get("/api/stream")
def api_stream():
    def gen():
        while True:
            with CACHE_LOCK:
                sess = CACHE.get("sessions") or {}
                res = CACHE.get("resources") or {}
                back = CACHE.get("backlog") or {}
            jobs = [j.public() for j in QUEUE.jobs.values()]
            yield _sse({"overview": src.overview(sess, res, back, jobs), "resources": res, "jobs": jobs})
            time.sleep(2)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/health")
def api_health():
    return {"ok": True, "version": "0.1.0", "at": int(time.time() * 1000),
            "keyPresent": bool(os.environ.get("QIANWEN_API_KEY"))}


@app.on_event("startup")
def _startup():
    for job_id in ("resources", "sessions", "backlog"):
        job = QUEUE.jobs[job_id]
        job.nextRunAt = time.time()
        QUEUE.push(job)


if __name__ == "__main__":
    print(f"止观AI 任务看板 → http://{HOST}:{PORT}  （只听本机回环，Ctrl+C 停）")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
