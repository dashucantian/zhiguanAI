#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""块三「等我一句话」薄发射器（纯 stdlib、零出网、单出口）。

读 01_项目管理/待裁单.md 主表「候编号」行，号列无「已决」者为活条；
「之订正」附行不另占号 ⇒ 剔（件里同时写「按附行剔算 N」与「不剔算 M」两句，
协调位 2026-11-11 02:5x 令：理由不写，下一个人会按 M 重算然后再也不信这个数）。
已挂时长现算＝发射时刻 − 号列〔落单时刻〕；只写 data/pending-rulings.js。
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "data" / "pending-rulings.js"
SRC = ROOT / "01_项目管理" / "待裁单.md"

ROW_RE = re.compile(r"^\|\s*\*\*候编号\*\*")
FILED_RE = re.compile(r"〔(20\d{2}-\d{1,2}-\d{1,2})\s+(\d{1,2}:[0-5]\d|\d{1,2}:\d[xX])")
FILED_RAW_RE = re.compile(r"〔[^〕]*〕")
TITLE_RE = re.compile(r"\*\*(.+?)\*\*")
FLAG_RE = re.compile(r"⚑([^〕]+)")

CONSEQ = [
    ("对外发消息", "不能对外发问，两期回执一直缺"),
    ("提交放行", "两件底件不入 git，本机独有"),
    ("涉规约", "不立规，读群仍无触发时点"),
    ("模型线归属", "谁去试悬空，实测不启动"),
    ("共用程序件", "看门狗照旧只盯 8791，桥哑无人知"),
    ("对外发布", "长连接不开，DSH 退不了"),
]
FALLBACK = "不裁则维持现状，不得动作"


def redact(s):
    return s.replace("费梦玲", "执行人").replace("宗国法师", "法师")


def fuzzy_min(s):
    return int(s.replace("x", "0").replace("X", "0"))


def hang_text(hours):
    if hours < 24:
        return "%d 小时" % round(hours)
    return "%.1f 天" % (hours / 24)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not SRC.exists():
        print("拒发：待裁单不存在 %s" % SRC)
        return 2
    now = datetime.datetime.now()
    rows, appendix = [], []
    for lineno, line in enumerate(SRC.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        st = line.strip()
        if not ROW_RE.match(st):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 2 or "已决" in cells[0]:
            continue
        if "之订正" in cells[0]:
            appendix.append({"line": lineno, "head": redact(cells[0][:60])})
            continue
        tm = TITLE_RE.search(cells[1])
        title = redact(tm.group(1)) if tm else redact(cells[1][:24])
        fm = FLAG_RE.search(cells[0])
        category = fm.group(1).strip() if fm else ""
        consequence = FALLBACK
        for key, text in CONSEQ:
            if key in category:
                consequence = text
                break
        row = {
            "line": lineno,
            "title": title,
            "category": category,
            "consequence": consequence,
        }
        dm = FILED_RE.search(cells[0])
        if dm:
            d = dm.group(1).split("-")
            hh, mm = dm.group(2).split(":")
            dt = datetime.datetime(int(d[0]), int(d[1]), int(d[2]), int(hh), fuzzy_min(mm))
            hours = (now - dt).total_seconds() / 3600
            raw = FILED_RAW_RE.search(cells[0])
            row.update({
                "filedRaw": raw.group(0) if raw else dm.group(0),
                "filedAt": dt.strftime("%Y-%m-%d %H:%M"),
                "hours": round(hours, 1),
                "hang": hang_text(hours),
                "recompute": "已挂＝发射时刻 − 号列〔落单时刻〕（x 作 0）；人工复算：读 待裁单.md :%d 号列〔〕内时刻，与当前时刻相减" % lineno,
            })
        else:
            row.update({"filedRaw": None, "filedAt": None, "hours": None,
                        "hang": "未记", "recompute": "号列无〔落单时刻〕，已挂未记"})
        rows.append(row)
    if not rows and not appendix:
        print("拒发：一条候编号行都解析不出（%s）" % SRC)
        return 2
    rows.sort(key=lambda r: (r["hours"] is None, -(r["hours"] or 0), r["line"]))
    payload = {
        "checkedAtLocal": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": SRC.relative_to(ROOT).as_posix(),
        "count": len(rows),
        "countWithAppendix": len(rows) + len(appendix),
        "rows": rows,
        "appendix": appendix,
        "caliber": {
            "active": "检索面＝全件以「| **候编号**」起首的表行；活条＝号列无「已决」",
            "count": "按附行剔算 %d；不剔算 %d。剔的理由：「之订正」行是上一行候编号的读数订正附行（首格明写「之订正」），不另占候编号、不是独立候裁项 ⇒ 剔" % (len(rows), len(rows) + len(appendix)),
            "hang": "已挂＝发射时刻 − 号列〔落单时刻〕；模糊分 x 作 0；不足一天按小时；无〔落单时刻〕标「未记」排最后",
            "consequence": "按号列 ⚑ 类别映射固定一句（映射表见发射器源码 CONSEQ，具体类别优先于宽类别）；未覆盖类别用兜底句「" + FALLBACK + "」",
            "sort": "已挂时长降序（同长按行号升序）；未记排最后",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.PENDING_RULINGS = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    OUT.write_bytes(js.encode("utf-8"))
    print("已写 %s：活条 %d（按附行剔算）／%d（不剔）"
          % (OUT, len(rows), len(rows) + len(appendix)))
    return 0


if __name__ == "__main__":
    sys.exit(main())