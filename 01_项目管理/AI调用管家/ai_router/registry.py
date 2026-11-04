"""账本对账：拿账本里的任务号去任务登记那份正源对一遍。

口径照 W3 协调位 2026-11-04 裁（`信箱/engine/20261104-DSH-4ef78b3e_中枢任务号贯穿归口_v1.md` §二裁三）：
    合　　　TASK-YYYYMMDD-NN 且存在于任务登记
    未标记　允许，但必须单列可见
    其他　　外部号（像 ZG 号／窗口号）或笔误（近似现存号却不等于）——不猜、不改、不丢
"""

from __future__ import annotations

import re
from pathlib import Path

from . import store

# 仓根：<管家目录>/../../..
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REGISTRY_FILE = REPO_ROOT / "01_项目管理" / "任务登记.md"

TASK_ID_PATTERN = re.compile(r"TASK-\d{8}-\d{2}")

# 外部号的常见形态：飞书 ZG 号、窗口号（AI-026／W3／4ef78b3e 一类）。
EXTERNAL_PATTERNS = (
    re.compile(r"^ZG-\d+$", re.IGNORECASE),
    re.compile(r"^[A-Z]{2,4}\d{3,}$"),
    re.compile(r"^[0-9a-f]{8}$", re.IGNORECASE),
    re.compile(r"^AI-\d+", re.IGNORECASE),
)


def registry_ids(path: Path | None = None) -> set[str]:
    """任务登记里出现过的全部任务号（标题与正文引用都算——正源说有它就有它）。"""
    target = path or REGISTRY_FILE
    try:
        text = target.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return set()
    return set(TASK_ID_PATTERN.findall(text))


def _normalize(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def classify(value: str, known: set[str]) -> str:
    """把一个账本里的任务号判成 合／未标记／外部号／笔误。"""
    text = (value or "").strip()
    if not text or text == store.UNTAGGED:
        return "未标记"
    if text in known:
        return "合"
    if _normalize(text) in {_normalize(item) for item in known}:
        # 去掉分隔符后与某个已登记号完全一样：差的是写法，不是这条任务。
        return "笔误"
    for pattern in EXTERNAL_PATTERNS:
        if pattern.match(text):
            return "外部号"
    return "外部号"


def reconcile(month: str | None = None, path: Path | None = None) -> dict:
    """本月账本的任务号逐条对账，出一份三态分布。"""
    month = month or store.month_key()
    known = registry_ids(path)
    buckets: dict[str, dict] = {
        "合": {"次数": 0.0, "美元": 0.0, "任务号": set()},
        "未标记": {"次数": 0.0, "美元": 0.0, "任务号": set()},
        "外部号": {"次数": 0.0, "美元": 0.0, "任务号": set()},
        "笔误": {"次数": 0.0, "美元": 0.0, "任务号": set()},
    }
    for row in store.read_ledger():
        if row.get("月") != month:
            continue
        value = row.get("任务号") or store.UNTAGGED
        kind = classify(value, known)
        bucket = buckets[kind]
        bucket["次数"] += float(row.get("次数") or 1)
        bucket["美元"] += float(row.get("美元") or 0.0)
        bucket["任务号"].add(value)
    for bucket in buckets.values():
        bucket["任务号"] = sorted(bucket["任务号"])
    return {
        "月": month,
        "号集大小": len(known),
        "号集来源": str(path or REGISTRY_FILE),
        "分布": buckets,
    }


def workspace_rows(month: str | None = None) -> list[dict]:
    """账本里的工作区栏：填了没、路径在不在盘、是不是 worktree。"""
    month = month or store.month_key()
    out: dict[str, dict] = {}
    for row in store.read_ledger():
        if row.get("月") != month:
            continue
        workspace = (row.get("工作区") or "").strip()
        if not workspace:
            continue
        entry = out.setdefault(workspace, {"次数": 0.0, "美元": 0.0})
        entry["次数"] += float(row.get("次数") or 1)
        entry["美元"] += float(row.get("美元") or 0.0)
    rows = []
    for key, value in sorted(out.items(), key=lambda kv: -kv[1]["美元"]):
        path = Path(key)
        rows.append({
            "工作区": key,
            **value,
            "在盘": path.exists(),
            "是worktree": is_worktree(key),
        })
    return rows


def is_worktree(workspace: str) -> bool:
    """是不是隔离执行树：路径在仓内 _worktrees 之下，且那棵子目录确实在盘。"""
    if not workspace:
        return False
    try:
        path = Path(workspace).resolve()
    except OSError:
        return False
    parts = path.parts
    if "_worktrees" not in parts:
        return False
    index = parts.index("_worktrees")
    if index + 1 >= len(parts):
        return False
    return path.exists()


def expected_worktree(task_id: str) -> Path:
    """按脚手架的命名规矩，一个任务号对应的隔离树该在哪。"""
    slug = re.sub(r"[^A-Za-z0-9\-]", "-", task_id)
    return REPO_ROOT / "_worktrees" / slug


def expected_workspace(task_id: str) -> str:
    """任务号对应的隔离树真路径；不在盘就返回空。

    工作区栏只填实测存在的路径，不接受人随手写的字符串。
    """
    if not task_id or task_id == store.UNTAGGED:
        return ""
    try:
        path = expected_worktree(task_id)
    except OSError:
        return ""
    return str(path) if path.exists() else ""

