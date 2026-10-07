"""只读数据适配层：Qoder 会话／系统资源／维那看板快照／模型注册表。

铁律：
- 本模块只读，不写任何外部文件（state/ 目录除外，由 board_server 负责）。
- 不读对话正文（jsonl 的 message 内容一律跳过），只取元数据。
- 密钥只报 present/absent，永不返回、永不记录、永不入模型上下文。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import board_config as cfg

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
QODER_HOME = Path.home() / ".qoder-cn"
PROJ_KEY = "D--Project-zhiguanAI"
PROJ_DIR = QODER_HOME / "projects" / PROJ_KEY
TASKS_DIR = QODER_HOME / "tasks"
CONFIG_DIR = HERE / "config"
STATE_DIR = HERE / "state"
WEINA_DIRS = [REPO / "01_项目管理" / "任务关系图"]

TAIL_BYTES = 96 * 1024
META_TYPES = {"runtime-config", "last-prompt", "workspace-directories", "worktree-state"}


def _read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _load_config(name: str, fallback):
    """正源＝board_config.py（可入库）；config/*.json 若存在则本机覆盖（*.json 被 .gitignore 拦）。"""
    data = _read_json(CONFIG_DIR / name)
    return data if isinstance(data, dict) else fallback


# ─────────────────────────── Qoder 会话 ───────────────────────────

def _count_lines(path: Path) -> int:
    n = 0
    try:
        with open(path, "rb") as fh:
            while True:
                block = fh.read(1 << 20)
                if not block:
                    return n
                n += block.count(b"\n")
    except Exception:
        return n


def _tail_meta(path: Path) -> dict:
    """只解析文件尾部若干元数据记录，不碰 message 正文。"""
    meta = {}
    try:
        size = path.stat().st_size
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TAIL_BYTES))
            if size > TAIL_BYTES:
                fh.readline()
            raw = fh.read().decode("utf-8", errors="replace")
    except Exception:
        return meta
    for line in raw.splitlines():
        line = line.strip()
        if not line or '"type"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        kind = obj.get("type")
        if kind not in META_TYPES:
            continue
        if kind == "runtime-config":
            meta["model"] = obj.get("model")
            meta["contextWindow"] = obj.get("contextWindow")
            meta["reasoningEffort"] = obj.get("reasoningEffort")
        elif kind == "last-prompt":
            meta["lastPrompt"] = (obj.get("lastPrompt") or "")[:120]
        elif kind == "workspace-directories":
            meta["dirs"] = obj.get("directories") or []
    return meta


def _session_tasks(session_id: str) -> list[dict]:
    d = TASKS_DIR / session_id
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json"), key=lambda x: int(x.stem) if x.stem.isdigit() else 0):
        obj = _read_json(p)
        if not isinstance(obj, dict):
            continue
        out.append({
            "id": obj.get("id", p.stem),
            "subject": obj.get("subject", ""),
            "status": obj.get("status", "pending"),
            "activeForm": obj.get("activeForm"),
            "blockedBy": obj.get("blockedBy") or [],
        })
    return out


def _live_snapshot() -> dict:
    """由 AI 窗口经 MCP list_chat_sessions 刷新的活体快照（含 runtimeState）。"""
    obj = _read_json(STATE_DIR / "live_sessions.json")
    if not isinstance(obj, dict):
        return {}
    return obj


def scan_sessions(limit: int = 40, days: int = 45) -> dict:
    registry = _load_config("windows.json", cfg.windows_registry())
    known = {item.get("sessionId"): item for item in registry.get("windows", []) if item.get("sessionId")}
    snap = _live_snapshot()
    snap_at = snap.get("takenAt") or 0
    snap_rows = {row.get("sessionId"): row for row in snap.get("sessions", [])}
    snap_fresh = bool(snap_at) and (time.time() * 1000 - snap_at) < 180_000

    files = []
    if PROJ_DIR.is_dir():
        cutoff = time.time() - days * 86400
        for p in PROJ_DIR.glob("*.jsonl"):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff:
                continue
            files.append((st.st_mtime, st.st_size, p))
    files.sort(reverse=True)

    windows = []
    for mtime, size, path in files[:limit]:
        sid = path.stem
        meta = _tail_meta(path)
        tasks = _session_tasks(sid)
        done = sum(1 for t in tasks if t["status"] == "completed")
        reg = known.get(sid, {})
        live = snap_rows.get(sid, {})
        if snap_fresh and live:
            state = live.get("runtimeState", "未知")
            pending = live.get("pendingInteractionCount", 0)
        else:
            state = "活跃" if (time.time() - mtime) < 180 else "静默"
            pending = 0
        windows.append({
            "sessionId": sid,
            "label": reg.get("label") or live.get("title") or f"未登记窗口 {sid[:8]}",
            "window": reg.get("window"),
            "execClass": reg.get("execClass", "未验"),
            "session": reg.get("session"),
            "state": state,
            "stateSource": "MCP快照" if (snap_fresh and live) else "磁盘mtime推断",
            "pending": pending,
            "title": live.get("title"),
            "model": meta.get("model"),
            "contextWindow": meta.get("contextWindow"),
            "lastPrompt": meta.get("lastPrompt"),
            "updatedAt": int(mtime * 1000),
            "sizeKB": round(size / 1024),
            "lines": _count_lines(path),
            "taskTotal": len(tasks),
            "taskDone": done,
            "progress": round(done / len(tasks) * 100) if tasks else None,
            "tasks": tasks,
            "registered": sid in known,
        })
    return {
        "windows": windows,
        "snapshot": {
            "takenAt": snap_at,
            "fresh": snap_fresh,
            "source": "state/live_sessions.json",
            "note": "runtimeState 只能由 AI 窗口经 MCP list_chat_sessions 刷新；过期时按磁盘 mtime 推断活跃/静默",
        },
        "scannedAt": int(time.time() * 1000),
    }


# ─────────────────────────── 系统资源 ───────────────────────────

_NET_BASE = {"bytes_sent": 0, "bytes_recv": 0, "ts": 0.0}


def resources(top_n: int = 8) -> dict:
    import psutil

    if not getattr(resources, "_primed", False):
        psutil.cpu_percent(interval=None)
        resources._primed = True
    cpu = psutil.cpu_percent(interval=None)
    vm = psutil.virtual_memory()
    out = {
        "cpuPercent": cpu,
        "cpuCores": psutil.cpu_count(logical=True),
        "memTotalGB": round(vm.total / 1024 ** 3, 1),
        "memUsedGB": round(vm.used / 1024 ** 3, 1),
        "memPercent": vm.percent,
        "disks": [],
        "procs": [],
        "pyProcs": 0,
        "nodeProcs": 0,
        "sampledAt": int(time.time() * 1000),
    }
    for letter in ("C:", "D:"):
        try:
            du = psutil.disk_usage(letter + "\\")
            out["disks"].append({
                "mount": letter,
                "totalGB": round(du.total / 1024 ** 3, 1),
                "usedGB": round(du.used / 1024 ** 3, 1),
                "percent": du.percent,
            })
        except Exception:
            pass
    rows = []
    for pr in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = pr.info
            name = (info.get("name") or "").lower()
            if "python" in name:
                out["pyProcs"] += 1
            if "node" in name:
                out["nodeProcs"] += 1
            # PID 0/4 是 Windows 记账项（System Idle Process 常年 3000%+），进榜只会淹没真实负载
            if info["pid"] < 8:
                continue
            rows.append({
                "pid": info["pid"],
                "name": info.get("name") or "?",
                "cpu": round(info.get("cpu_percent") or 0.0, 1),
                "memMB": round((info.get("memory_info").rss if info.get("memory_info") else 0) / 1024 ** 2),
            })
        except Exception:
            continue
    rows.sort(key=lambda r: (r["cpu"], r["memMB"]), reverse=True)
    out["procs"] = rows[:top_n]

    try:
        net = psutil.net_io_counters()
        now = time.time()
        if _NET_BASE["ts"]:
            dt = max(now - _NET_BASE["ts"], 0.001)
            out["netUpKBs"] = round((net.bytes_sent - _NET_BASE["bytes_sent"]) / 1024 / dt, 1)
            out["netDownKBs"] = round((net.bytes_recv - _NET_BASE["bytes_recv"]) / 1024 / dt, 1)
        _NET_BASE.update(bytes_sent=net.bytes_sent, bytes_recv=net.bytes_recv, ts=now)
    except Exception:
        pass
    return out


# ─────────────────────────── 维那看板快照 ───────────────────────────

def _find_weina_snapshot() -> Path | None:
    best = None
    for root in WEINA_DIRS:
        if not root.is_dir():
            continue
        for p in root.rglob("_records_raw.json"):
            if best is None or p.stat().st_mtime > best.stat().st_mtime:
                best = p
    return best


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or ""))
            else:
                parts.append(str(item))
        return "、".join(p for p in parts if p)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "")
    return str(value)


def _pick(fields: list[str], *keywords) -> int | None:
    for i, name in enumerate(fields):
        for kw in keywords:
            if kw in name:
                return i
    return None


def backlog() -> dict:
    path = _find_weina_snapshot()
    if path is None:
        return {"ok": False, "reason": "未找到 _records_raw.json 快照", "rows": []}
    obj = _read_json(path)
    if not obj:
        return {"ok": False, "reason": "快照解析失败", "rows": [], "path": str(path)}
    data = obj.get("data") or {}
    fields = data.get("fields") or []
    raw_rows = data.get("data") or []
    idx = {
        "name": _pick(fields, "任务名", "名称"),
        "code": _pick(fields, "编号"),
        "stage": _pick(fields, "阶段"),
        "status": _pick(fields, "状态"),
        "owner": _pick(fields, "承担"),
        "window": _pick(fields, "执行窗口"),
        "ruling": _pick(fields, "裁决"),
        "rulingOk": _pick(fields, "裁决确认"),
        "accept": _pick(fields, "承接状态"),
        "acceptStamp": _pick(fields, "受理"),
        "updated": _pick(fields, "更新时间"),
        "planStart": _pick(fields, "计划开始"),
        "planEnd": _pick(fields, "计划截止"),
        "runState": _pick(fields, "运行状态"),
        "reason": _pick(fields, "延后原因"),
    }

    def cell(row, key):
        i = idx[key]
        if i is None or i >= len(row):
            return ""
        return _cell_text(row[i])

    rows = []
    for row in raw_rows:
        rec = {k: cell(row, k) for k in idx}
        rec["name"] = rec["name"][:160]
        rows.append(rec)

    by_status: dict[str, int] = {}
    for r in rows:
        key = r.get("status") or "（空）"
        by_status[key] = by_status.get(key, 0) + 1

    need_accept = [r for r in rows if ("裁决" in (r.get("ruling") or "")) and not (r.get("acceptStamp") or "").strip()]
    qc = (data.get("query_context") or {})
    return {
        "ok": True,
        "path": str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path),
        "pulledAt": qc.get("pulled_at"),
        "total": data.get("total"),
        "fields": fields,
        "rows": rows,
        "byStatus": by_status,
        "needAccept": len(need_accept),
        "needAcceptRows": [{"code": r.get("code"), "name": r.get("name")[:60], "status": r.get("status")} for r in need_accept[:20]],
        "readAt": int(time.time() * 1000),
    }


# ─────────────────────────── 模型注册表 ───────────────────────────

def models_registry() -> dict:
    reg = _load_config("models.json", cfg.models_registry_raw())
    out = []
    for m in reg.get("models", []):
        env_name = m.get("keyEnv") or ""
        out.append({
            "id": m.get("id"),
            "label": m.get("label"),
            "provider": m.get("provider"),
            "kind": m.get("kind", "chat"),
            "baseUrl": m.get("baseUrl"),
            "model": m.get("model"),
            "keyEnv": env_name,
            "keyPresent": bool(env_name and os.environ.get(env_name)),
            "egress": m.get("egress", "三级（可出网）"),
            "note": m.get("note", ""),
            "isDefault": bool(m.get("isDefault")),
        })
    state = _read_json(STATE_DIR / "model_probe.json") or {}
    for m in out:
        m["lastProbe"] = state.get(m["id"])
    return {
        "models": out,
        "voice": reg.get("voice") or cfg.VOICE,
        "default": next((m["id"] for m in out if m["isDefault"]), (out[0]["id"] if out else None)),
        "keyHint": "密钥只从环境变量读取（设置千问密钥.ps1 / qianwen-key-setup.ps1），本看板不存、不显示、不上传",
    }


def get_model(model_id: str | None) -> dict | None:
    reg = _load_config("models.json", cfg.models_registry_raw())
    models = reg.get("models", [])
    if model_id:
        for m in models:
            if m.get("id") == model_id:
                return m
    for m in models:
        if m.get("isDefault"):
            return m
    return models[0] if models else None


# ─────────────────────────── 汇总 ───────────────────────────

def overview(sessions: dict, res: dict, board: dict, jobs: list[dict]) -> dict:
    wins = sessions.get("windows", [])
    running = [w for w in wins if w["state"] in ("running", "活跃")]
    tasks_all = [t for w in wins for t in w["tasks"]]
    done = sum(1 for t in tasks_all if t["status"] == "completed")
    inprog = sum(1 for t in tasks_all if t["status"] == "in_progress")
    return {
        "windowTotal": len(wins),
        "windowRunning": len(running),
        "windowRegistered": sum(1 for w in wins if w["registered"]),
        "taskTotal": len(tasks_all),
        "taskDone": done,
        "taskInProgress": inprog,
        "taskPending": len(tasks_all) - done - inprog,
        "backlogTotal": board.get("total") or 0,
        "backlogNeedAccept": board.get("needAccept", 0),
        "backlogPulledAt": board.get("pulledAt"),
        "cpuPercent": res.get("cpuPercent"),
        "memPercent": res.get("memPercent"),
        "jobTotal": len(jobs),
        "jobPaused": sum(1 for j in jobs if j.get("paused")),
        "jobRunning": sum(1 for j in jobs if j.get("state") == "running"),
        "snapshotFresh": sessions.get("snapshot", {}).get("fresh", False),
        "at": int(time.time() * 1000),
    }
