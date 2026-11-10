# -*- coding: utf-8 -*-
"""群轮询台账 · W5｜群面 的取数件

只做一件事：把两个飞书群的新消息增量拉下来，追加进台账（只追加，不改旧行）。
不发任何消息、不改任何配置。

用法：
    python 群轮询台账.py            # 增量拉一次
    python 群轮询台账.py --baseline # 只记"现在到哪儿了"，不写台账（首次建立游标用）

台账字段（一行一条 JSON）：
    ts 抓取时刻 / chat 群名 / chat_id / msg_time 消息时刻 / message_id /
    sender 发送者（open_id 前 12 位或 bot app_id 前 12 位）/ msg_type /
    text 正文（文本类；其它类型记类型名）/ level 层级标（待判填 "1?"）/ replied 是否已回
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(BASE, "群互动台账.jsonl")
STATE = os.path.join(BASE, "轮询游标.json")

# 法师 2026-11-10 22:5x 确认：机器人值守的就是这两个群
CHATS = [
    ("止观ai先锋小群", "oc_3f032d05ec5b7615c0353379c66f6cfa"),
    ("第四届21天基础止观筹备组（大群）", "oc_8141574ee978e0ea50ce251fdbf2529c"),
]

def _resolve_lark() -> list[str]:
    """Windows 上 lark-cli 是 shell 脚本，Python 起不动；优先找同目录 .cmd，用 cmd /c 调。"""
    cands = [os.environ.get("LARK_CLI"),
             os.path.join(os.environ.get("QODER_HOME", r"C:\Users\tiand\.qoder-cn"),
                          r"plugins\cache\qoder-marketplace\lark\0.1.1\bin\lark-cli.cmd")]
    for c in cands:
        if c and os.path.exists(c):
            return [os.environ.get("COMSPEC", "cmd"), "/c", c]
    import shutil as _sh
    w = _sh.which("lark-cli.cmd") or _sh.which("lark-cli")
    if w:
        return [os.environ.get("COMSPEC", "cmd"), "/c", w] if w.lower().endswith(".cmd") else [w]
    return ["lark-cli"]


LARK = _resolve_lark()


def _run(args: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(args, capture_output=True)
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def load_state() -> dict:
    if os.path.exists(STATE):
        with open(STATE, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    return {}


def save_state(state: dict) -> None:
    with open(STATE, "wb") as f:
        f.write(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"))


def append(rows: list[dict]) -> None:
    if not rows:
        return
    with open(LEDGER, "ab") as f:
        for r in rows:
            f.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))


def fetch(chat_id: str, since: str | None) -> tuple[list[dict], str]:
    """拉一次消息。since 为空则只取最近 20 条建游标。"""
    args = LARK + ["im", "+chat-messages-list", "--chat-id", chat_id,
                   "--order", "asc", "--as", "user", "--no-reactions",
                   "--page-size", "50"]
    if since:
        args += ["--start", since]
    else:
        args += ["--order", "desc", "--page-size", "5"]
    rc, out, err = _run(args)
    if rc != 0 or not out.strip():
        raise RuntimeError("拉取失败 rc=%d err=%s" % (rc, err[:200]))
    data = json.loads(out)
    msgs = data.get("data", {}).get("messages", []) or []
    if not since:
        msgs = list(reversed(msgs))
    return msgs, out


def main() -> int:
    baseline = "--baseline" in sys.argv
    state = load_state()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    total_new = 0
    for name, cid in CHATS:
        since = None if baseline else state.get(cid)
        try:
            msgs, _ = fetch(cid, since)
        except Exception as exc:  # noqa: BLE001
            print("[X] %s 拉取失败：%s" % (name, exc))
            continue
        rows = []
        latest = since
        for m in msgs:
            mt = m.get("create_time") or ""
            if latest and mt and mt <= latest:
                continue
            sender = (m.get("sender") or {}).get("id") or ""
            rows.append({
                "ts": now,
                "chat": name,
                "chat_id": cid,
                "msg_time": mt,
                "message_id": m.get("message_id"),
                "sender": sender[:12],
                "sender_kind": (m.get("sender") or {}).get("id_type"),
                "msg_type": m.get("msg_type"),
                "text": (m.get("content") or "")[:500],
                "level": "1?",
                "replied": False,
            })
            if mt and (latest is None or mt > latest):
                latest = mt
        if latest:
            state[cid] = latest
        if baseline:
            print("[基线] %-30s 最新游标=%s（未写台账）" % (name, latest))
        else:
            append(rows)
            total_new += len(rows)
            print("[拉取] %-30s 新消息 %d 条（游标 %s → %s）" % (name, len(rows), since, latest))
    save_state(state)
    if not baseline:
        print("本轮新增合计 %d 条；台账 %s" % (total_new, LEDGER))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())