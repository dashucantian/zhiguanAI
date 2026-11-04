"""本机探针：从 opencode stats 读本机真实用量。

这是纯本机读取，不出网、不碰凭据。它只能看见本机 opencode 客户端的账；
别的客户端（Claude Code、Codex 等）直接打 Go 端点的用量，不在这里。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import store

_MODEL_LINE = re.compile(r"^\s*│\s*([^\s│][^│]*?)\s*$")
_FIELD = re.compile(r"^\s*│\s*(.+?)\s{2,}(.+?)\s*│\s*$")
_NUMBER = re.compile(r"^([\d,.]+)\s*([KMB]?)$")
_COST = re.compile(r"^\$([\d,.]+)$")


def _to_number(text: str) -> float:
    text = text.strip().replace(",", "")
    match = _NUMBER.match(text)
    if match:
        value = float(match.group(1))
        suffix = match.group(2)
        if suffix == "K":
            return value * 1_000
        if suffix == "M":
            return value * 1_000_000
        if suffix == "B":
            return value * 1_000_000_000
        return value
    cost = _COST.match(text)
    if cost:
        return float(cost.group(1))
    return 0.0


def parse_stats(text: str) -> dict:
    totals: dict[str, float] = {}
    models: list[dict] = []
    section = ""
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if "OVERVIEW" in line:
            section = "overview"
            continue
        if "COST & TOKENS" in line:
            section = "totals"
            continue
        if "MODEL USAGE" in line:
            section = "models"
            continue
        if "TOOL USAGE" in line:
            section = "tools"
            continue
        if section == "overview":
            match = _FIELD.match(line)
            if match:
                totals[match.group(1).strip()] = _to_number(match.group(2))
            continue
        if section == "totals":
            match = _FIELD.match(line)
            if match:
                totals[match.group(1).strip()] = _to_number(match.group(2))
            continue
        if section == "models":
            if "│" not in line:
                continue
            cells = [c.strip() for c in line.strip("│").split("│")]
            if len(cells) == 1 and cells[0]:
                if current:
                    models.append(current)
                current = {"模型": cells[0]}
                continue
            if len(cells) == 2 and current is not None:
                key = cells[0].replace("Tokens", "").strip()
                current[key] = _to_number(cells[1])
    if current:
        models.append(current)
    for model in models:
        name = model.get("模型", "")
        if "/" in name:
            model["模型"] = name.split("/")[-1]
    return {"总计": totals, "模型": models}


def resolve_command() -> list[str] | None:
    """找出真正能跑的 opencode 命令。

    Windows 上 PATH 里通常是 npm 生成的 .cmd 外壳，subprocess 直接 exec 不了，
    所以顺着 npm 目录找底下的真实可执行体。
    """
    override = os.environ.get("OPENCODE_BIN")
    if override and Path(override).exists():
        return [override]
    found = shutil.which("opencode.exe") or shutil.which("opencode")
    if found:
        if found.lower().endswith((".exe", ".bat", ".cmd")):
            return [found]
        return [found]
    npm_root = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "opencode-ai" / "bin"
    for name in ("opencode.exe", "opencode"):
        candidate = npm_root / name
        if candidate.exists():
            return [str(candidate)]
    return None


def read_stats(models: int = 20, timeout: float = 20.0) -> dict:
    command = resolve_command()
    if command is None:
        return {"可用": False, "原因": "本机没找到 opencode 命令（PATH 里没有，也不在 npm 目录）"}
    try:
        completed = subprocess.run(
            command + ["stats", "--models", str(models)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"可用": False, "原因": f"调用 opencode stats 失败：{exc}"}
    if completed.returncode != 0:
        return {"可用": False, "原因": (completed.stderr or "").strip()[:200] or "opencode stats 返回非零"}
    result = parse_stats(completed.stdout)
    result["可用"] = True
    result["读数时刻"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return result


def import_to_ledger(stats: dict) -> int:
    """把本机 opencode 的按模型统计写进账本（同一模型同一月只记一次总额）。"""
    if not stats.get("可用"):
        return 0
    month = store.month_key()
    existing = store.spend_by_model(month)
    written = 0
    for model in stats.get("模型", []):
        name = model.get("模型")
        if not name:
            continue
        cost = float(model.get("Cost", 0.0) or 0.0)
        if cost <= 0:
            continue
        already = existing.get(name, 0.0)
        delta = round(cost - already, 6)
        if delta <= 0:
            continue
        store.append_ledger(
            {
                "渠道": "opencode",
                "模型": name,
                "美元": delta,
                "次数": int(model.get("Messages", 0) or 0),
                "输入": int(model.get("Input", 0) or 0),
                "输出": int(model.get("Output", 0) or 0),
                "缓存读": int(model.get("Cache Read", 0) or 0),
                "说明": "本机 opencode stats 回填",
            }
        )
        written += 1
    return written
