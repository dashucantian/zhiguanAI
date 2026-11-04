"""本地账本与额度快照。

数据一律落在本目录的「数据」子目录，不入库、不出网。
账本是追加式的 JSONL，每行一笔；额度快照是一个 JSON 文件，随时可被后台读数覆盖。
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AI_ROUTER_DATA_DIR") or (BASE_DIR / "数据"))
QUOTA_FILE = DATA_DIR / "额度.json"
LEDGER_FILE = DATA_DIR / "账本.jsonl"
TASK_FILE = DATA_DIR / "当前任务.json"

CHANNEL_LABEL = {"opencode": "OpenCode Go", "bailian": "百炼 Token Plan", "qoder": "Qoder 积分"}

UNTAGGED = "未标记"

_SAFE_TASK = re.compile(r"[^A-Za-z0-9_.:\-\u4e00-\u9fff]")
_UNSAFE_TEXT = re.compile(r"[\x00-\x1f\x7f|]")


def clean_task_id(value) -> str:
    """任务号只留字母数字与几个记号；换行、竖杠、空格一律换成横杠，否则能拼出一条假日志。"""
    text = str(value or "").strip()
    if not text:
        return ""
    text = _SAFE_TASK.sub("-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:64]


def clean_workspace(value) -> str:
    text = _UNSAFE_TEXT.sub("", str(value or "").strip())
    return text[:160]


def set_current_task(task_id: str, workspace: str = "") -> dict:
    """本机「当前任务」：一次设定，所有客户端的调用都按这个任务号记账。"""
    _ensure_dir()
    data = {
        "任务号": clean_task_id(task_id),
        "工作区": clean_workspace(workspace),
        "设定时刻": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    TASK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_current_task() -> dict:
    try:
        data = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def month_key(ts: float | None = None) -> str:
    return time.strftime("%Y-%m", time.localtime(ts if ts is not None else time.time()))


def today_key(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts if ts is not None else time.time()))


def load_quota() -> dict:
    if not QUOTA_FILE.exists():
        return {}
    try:
        return json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_quota(data: dict) -> None:
    _ensure_dir()
    data["录入时刻"] = time.strftime("%Y-%m-%d %H:%M:%S")
    QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pools(data: dict, channel: str) -> list[dict]:
    entry = data.get(channel)
    if not entry:
        return []
    if isinstance(entry, dict) and "池" in entry:
        return entry["池"]
    # 旧格式：单条额度，迁成单池
    return [{
        "名称": entry.get("名称", "默认"),
        "剩余": entry.get("剩余", 0),
        "总额": entry.get("总额"),
        "单位": entry.get("单位", "Credits"),
        "备注": entry.get("备注", ""),
    }]


def set_quota(channel: str, remaining: float, total: float | None = None, unit: str = "Credits", note: str = "") -> dict:
    data = load_quota()
    entry = data.get(channel, {})
    entry.update({"剩余": remaining, "总额": total if total is not None else entry.get("总额"), "单位": unit})
    if note:
        entry["备注"] = note
    data[channel] = entry
    save_quota(data)
    return data


def set_pool(channel: str, pool: str, remaining: float, total: float | None = None,
             unit: str = "Credits", note: str = "", expires: str = "", resets: str = "") -> dict:
    """一个渠道可以分多个池（如 Qoder 的套餐内/资源包/专属积分），各池到期日不同，必须分开记。"""
    data = load_quota()
    pools = _pools(data, channel)
    entry = {
        "名称": pool,
        "剩余": remaining,
        "总额": total,
        "单位": unit,
        "到期": expires,
        "重置": resets,
        "备注": note,
    }
    pools = [p for p in pools if p.get("名称") != pool] + [entry]
    data[channel] = {"池": pools}
    save_quota(data)
    return data


def get_pools(channel: str) -> list[dict]:
    return _pools(load_quota(), channel)


def pool_remaining(channel: str, unit: str | None = None) -> float:
    pools = get_pools(channel)
    if unit:
        pools = [p for p in pools if p.get("单位") == unit]
    return sum(float(p.get("剩余") or 0.0) for p in pools)


def append_ledger(record: dict) -> dict:
    _ensure_dir()
    record = dict(record)
    record.setdefault("时刻", time.strftime("%Y-%m-%d %H:%M:%S"))
    record.setdefault("月", month_key())
    record.setdefault("日", today_key())
    record.setdefault("任务号", UNTAGGED)
    with LEDGER_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_ledger() -> list[dict]:
    if not LEDGER_FILE.exists():
        return []
    rows = []
    for line in LEDGER_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def spend_by_model(month: str | None = None) -> dict[str, float]:
    month = month or month_key()
    out: dict[str, float] = defaultdict(float)
    for row in read_ledger():
        if row.get("月") != month:
            continue
        if row.get("渠道") != "opencode":
            continue
        out[row.get("模型", "未知")] += float(row.get("美元") or 0.0)
    return dict(out)


def spend_by_channel(month: str | None = None, day: str | None = None) -> dict[str, dict[str, float]]:
    month = month or month_key()
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"美元": 0.0, "Credits": 0.0, "次数": 0.0})
    for row in read_ledger():
        if row.get("月") != month:
            continue
        if day is not None and row.get("日") != day:
            continue
        bucket = out[row.get("渠道", "未知")]
        bucket["美元"] += float(row.get("美元") or 0.0)
        bucket["Credits"] += float(row.get("Credits") or 0.0)
        bucket["次数"] += 1
    return {k: dict(v) for k, v in out.items()}


def spend_by_task(month: str | None = None) -> dict[str, dict]:
    """按任务号聚合：这个月每条任务各花了多少、走的是哪些模型。"""
    month = month or month_key()
    out: dict[str, dict] = {}
    for row in read_ledger():
        if row.get("月") != month:
            continue
        key = row.get("任务号") or UNTAGGED
        bucket = out.setdefault(key, {"美元": 0.0, "Credits": 0.0, "次数": 0.0,
                                     "输入": 0, "输出": 0, "模型": set()})
        bucket["美元"] += float(row.get("美元") or 0.0)
        bucket["Credits"] += float(row.get("Credits") or 0.0)
        bucket["次数"] += float(row.get("次数") or 1)
        bucket["输入"] += int(row.get("输入") or 0)
        bucket["输出"] += int(row.get("输出") or 0)
        bucket["模型"].add(row.get("模型") or "未知")
    for bucket in out.values():
        bucket["模型"] = "、".join(sorted(bucket["模型"]))
    return out
