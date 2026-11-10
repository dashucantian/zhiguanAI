#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双轴交汇跑批发射器（薄解析器，不复制任何业务判据）。

外环回执数：读协调位回执件 §三 逐条定性表，数「✅外环回执」行；
  并与 §二 凭据列里 om_ 消息 id 枚数互核，两数不符 ⇒ 不写文件、退码非零、两数都打印。
内轴判卷通过数：读留证面清单（本件 CONFIG 列明），数「总判：通过」命中条数；
  v2.1 口径＝无红线一票否决＋总分达线，留证件以「总判：」行自报，本件只数不判。
只写 data/dual-axis.js 一个出口；纯 stdlib、零出网、零第三方库。
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # 仓库根（看板根/05_产品与开发/关系场域活看板 → 上两级）
OUT = HERE / "data" / "dual-axis.js"

OUTER_SRC = ROOT / "01_项目管理" / "20261110_W3_AI034_外环第一条回执件_止观ai先锋小群_v1.md"
INNER_SOURCES = [
    ROOT / "01_项目管理" / "20261110_W4_真实判卷演练_v1.md",
]


def parse_outer(text: str):
    entries = []
    in_table = False
    for line in text.splitlines():
        st = line.strip()
        if st.startswith("## 三、"):
            in_table = True
            continue
        if in_table and st.startswith("## 四、"):
            break
        if not in_table or not st.startswith("|"):
            continue
        cells = [c.strip() for c in st.strip("|").split("|")]
        if len(cells) < 6 or cells[0] in ("#", "---"):
            continue
        if "✅外环回执" in cells[5]:
            entries.append({"no": cells[0], "time": cells[1], "sender": cells[3],
                            "kind": cells[2], "note": cells[5]})
    ids = re.findall(r"om_[0-9a-zA-Z]+", text)
    return entries, len(ids)


def parse_inner(paths):
    hits = []
    for p in paths:
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"总判[：:]\s*(通过|不通过)", t):
            hits.append({"file": p.relative_to(ROOT).as_posix(), "verdict": m.group(1)})
    passed = [h for h in hits if h["verdict"] == "通过"]
    return passed, hits


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not OUTER_SRC.exists():
        print("拒发：外环回执件不存在 %s" % OUTER_SRC)
        return 2
    outer_text = OUTER_SRC.read_text(encoding="utf-8", errors="replace")
    entries, id_count = parse_outer(outer_text)
    if len(entries) != id_count:
        print("拒发：三节勾标回执行=%d 与 二节 om_ id 数=%d 不符" % (len(entries), id_count))
        return 2
    passed, hits = parse_inner(INNER_SOURCES)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "checkedAtLocal": now,
        "outer": {
            "value": len(entries),
            "entries": entries,
            "source": OUTER_SRC.relative_to(ROOT).as_posix(),
            "recompute": "数回执件 §三 表内定性列含「✅外环回执」的行数，并与 §二 凭据列 om_ 消息 id 枚数互核（两数须同）",
        },
        "inner": {
            "value": len(passed),
            "verdicts": hits,
            "sources": [p.relative_to(ROOT).as_posix() for p in INNER_SOURCES],
            "standard": "01_项目管理/20261110_W4_L4-01判卷标准_v2.1.md（无红线一票否决＋总分达线）",
            "recompute": "在留证面各件 grep「总判：通过」行数求和；现留证面唯一一次判卷总判为不通过，故为 0",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.DUAL_AXIS = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    OUT.write_bytes(js.encode("utf-8"))
    print("已写 %s：外环 %d 条（互核 om_ id %d 相符）、内轴通过 %d／判卷留证 %d 次"
          % (OUT, len(entries), id_count, len(passed), len(hits)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
