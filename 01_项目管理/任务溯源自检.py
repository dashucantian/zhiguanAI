# -*- coding: utf-8 -*-
"""任务溯源自检 v1（中枢 v0 · 第 1 步配套；只读、零外联）

为什么要有它：
    「触发来源」「最近活动」两个字段如果只是写在纸上，它就又成了一条「没有闸的规矩」
    （判语 033／坑 044 同型）。本脚本把两件事变成**可判**：

      ① 每条未销任务，两个字段是否齐；
      ② 字段里引用的材料**是否真的解析得到**——文件名要能在盘上找到，
         提交号要能被 git 认出；带省略号（…）的缩写一律判 FAIL（那是最常见的一种假引用）。

跑法：python 01_项目管理/任务溯源自检.py
退码：0＝全过；1＝有问题；2＝登记件读不到
纪律：解析不到就记 FAIL，不记 WARN、不记「未验」——引用解析不到＝这条登记不能回查。
"""
import re
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "01_项目管理" / "任务登记.md"
HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")
ELLIPSIS = ("…", "...")


def git_has_commit(sha: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-t", sha],
            capture_output=True, text=True, timeout=20,
        )
        return r.returncode == 0 and "commit" in r.stdout
    except Exception:  # noqa: BLE001
        return False


def find_file(name: str):
    """按文件名在仓内找；找不到返回 None。"""
    for p in ROOT.rglob(name):
        if p.is_file():
            return p
    return None


def main():
    if not LEDGER.exists():
        print(f"[FAIL] 登记件不存在：{LEDGER}")
        return 2

    lines = LEDGER.read_text(encoding="utf-8", errors="replace").splitlines()
    tasks = {}          # id -> dict
    cur = None
    for ln in lines:
        m = re.match(r"^### (TASK-\S+)\s*$", ln)
        if m:
            cur = m.group(1)
            tasks[cur] = {"trigger": None, "activity": None, "closed": False}
            continue
        if not cur:
            continue
        if ln.startswith("- 状态：") and "已销" in ln:
            tasks[cur]["closed"] = True
        elif ln.startswith("- 触发来源："):
            tasks[cur]["trigger"] = ln.split("：", 1)[1].strip()
        elif ln.startswith("- 最近活动："):
            tasks[cur]["activity"] = ln.split("：", 1)[1].strip()

    fails, oks = [], []
    live = {k: v for k, v in tasks.items() if not v["closed"]}

    # 规则（2026-11-03 定）：
    #   触发来源——必须带可解析指针（文件或提交号）；这是「回得到原始材料」的硬要求。
    #   最近活动——必须带时刻（MM-DD 或 HH:MM）；指针可选（有些落点就是一次销项，无件）。
    TIME_RE = re.compile(r"\d{1,2}-\d{1,2}|\d{1,2}:\d{2}")

    for tid, t in live.items():
        trigger = t["trigger"]
        if not trigger:
            fails.append(f"{tid} 缺「触发来源」")
        else:
            refs = re.findall(r"`([^`]+)`", trigger)
            if not refs:
                fails.append(f"{tid}「触发来源」无指针（须至少一个 `文件名`／`提交号`）")
            for ref in refs:
                if any(e in ref for e in ELLIPSIS):
                    fails.append(f"{tid}「触发来源」缩写不可解析：{ref}")
                    continue
                if HASH_RE.match(ref):
                    (oks if git_has_commit(ref) else fails).append(
                        f"{tid}「触发来源」提交 {ref} " + ("在库" if git_has_commit(ref) else "查无此笔"))
                    continue
                if find_file(ref):
                    oks.append(f"{tid}「触发来源」文件 {ref} 在盘")
                else:
                    fails.append(f"{tid}「触发来源」文件解析不到：{ref}")

        act = t["activity"]
        if not act:
            fails.append(f"{tid} 缺「最近活动」")
        elif not TIME_RE.search(act):
            fails.append(f"{tid}「最近活动」无时刻（须 MM-DD 或 HH:MM）")
        else:
            bad = False
            for ref in re.findall(r"`([^`]+)`", act):
                if any(e in ref for e in ELLIPSIS):
                    fails.append(f"{tid}「最近活动」缩写不可解析：{ref}"); bad = True
                elif HASH_RE.match(ref) and not git_has_commit(ref):
                    fails.append(f"{tid}「最近活动」提交 {ref} 查无此笔"); bad = True
                elif not HASH_RE.match(ref) and not find_file(ref):
                    fails.append(f"{tid}「最近活动」文件解析不到：{ref}"); bad = True
            if not bad:
                oks.append(f"{tid}「最近活动」时刻在（{act[:16]}）")

    for x in oks:
        print("[OK] " + x)
    for x in fails:
        print("[FAIL] " + x)
    print(f"[END] 未销任务={len(live)} 指针通过={len(oks)} 问题={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())