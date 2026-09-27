# -*- coding: utf-8 -*-
"""登记分片索引生成器（通用壳·幂等只读本目录，只写 00_总索引.md）。
用法：放进你的"登记分片"目录，`python 生成索引.py`。
"""
import io, os, re, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "00_总索引.md")

rows = []
for fn in sorted(os.listdir(HERE)):
    if not fn.endswith(".md") or fn in ("README.md", "00_总索引.md"):
        continue
    if not (fn.startswith("D-") or fn.startswith("KZ-")):
        continue
    body = ""
    try:
        body = io.open(os.path.join(HERE, fn), encoding="utf-8").read()
    except Exception:
        pass
    m = re.search(r"^#\s+(.+)$", body, re.M)
    rows.append(f"| {fn[:-3]} | {(m.group(1).strip() if m else '（无标题行）')[:60]} |")

now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
txt = ("# 登记总索引（自动生成，勿手改）\n\n"
       "> 派生视图非真相源；重跑 `python 生成索引.py` 即修复（其未提交状态不算滞留事故）。\n"
       f"> 最近生成：{now}\n\n"
       "| 编号 | 标题 |\n|---|---|\n" +
       "\n".join(rows if rows else ["| （暂无） | 新条目按 README 命名落本目录 |"]) + "\n")
io.open(OUT, "w", encoding="utf-8", newline="\n").write(txt)
print("写出", OUT, "共", len(rows), "条")
