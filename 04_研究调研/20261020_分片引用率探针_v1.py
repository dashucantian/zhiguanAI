# -*- coding: utf-8 -*-
"""
分片引用率探针 v1（只读，不改项目盘）
用途：为《AgentWorld 对我方价值建构》一文提供"贡献率"（CCE 思路）的本地最低限度读数。
口径见同目录 20261020_AgentWorld多智能体协作基准_对我方协作与产品的价值建构_v1.md §四.2。

用法：
    python 20261020_分片引用率探针_v1.py                 # 剔除扫描器（严尺，默认）
    python 20261020_分片引用率探针_v1.py --with-scanners # 含 C3 扫描器与巡检日志（宽尺）

读数含义：某分片文件名（去 .md）在语料其它文件里出现过的"件数"。
    - 0 件 = 从未被任何下游件按名引用（不代表未被执行，只代表没留引用痕迹）
    - 该值只是"贡献"的下界代理，不是 CCE 本身。

边界：
    1. 只扫 01_项目管理\\登记分片、案例库、信箱 与仓库根 *.md，外加三份正式件；
       路径含「机密」「人格档案」「原始素材」一律跳过（L3 硬约束，规约 §四bis）。
    2. 不碰 02_修道班运营、不读原始脑电、不读学员档案。
    3. 纯读、无网络、无写入。
"""
import argparse
import json
import os
import re
import statistics

ROOT = r"D:\Project\zhiguanAI"
SHARD = os.path.join(ROOT, "01_项目管理", "登记分片")
ALWAYS_SKIP = {"00_总索引.md", "README.md", "悬案已销.txt", "周期哨台账.md"}
FORBIDDEN = ("机密", "人格档案", "原始素材")


def collect(include_scanners: bool):
    corpus = []

    def walk(d):
        for base, _, files in os.walk(d):
            for f in files:
                if not f.lower().endswith((".md", ".txt")):
                    continue
                p = os.path.join(base, f)
                if f in ALWAYS_SKIP:
                    continue
                if any(k in p for k in FORBIDDEN):
                    continue
                if not include_scanners and (f.startswith("C3-") or "巡检日志" in f):
                    continue
                corpus.append(p)

    walk(SHARD)
    walk(os.path.join(ROOT, "01_项目管理", "案例库"))
    walk(os.path.join(ROOT, "01_项目管理", "信箱"))
    for f in os.listdir(ROOT):
        p = os.path.join(ROOT, f)
        if os.path.isfile(p) and f.lower().endswith(".md"):
            corpus.append(p)
    for f in ("20261019_接班卡_交接程序固定件_v1.1.md", "待裁单.md"):
        p = os.path.join(ROOT, "01_项目管理", f)
        if os.path.exists(p):
            corpus.append(p)
    return corpus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-scanners", action="store_true")
    a = ap.parse_args()

    corpus = collect(a.with_scanners)
    texts = {}
    for p in corpus:
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                texts[p] = fh.read()
        except OSError:
            pass

    targets = sorted(
        f for f in os.listdir(SHARD)
        if re.match(r"^(D|KZ)-\d{4}-", f) and f.endswith(".md")
    )
    rows = []
    for t in targets:
        stem = t[:-3]
        by = [os.path.relpath(p, ROOT) for p, txt in texts.items()
              if os.path.basename(p) != t and stem in txt]
        rows.append({"file": t, "ref_files": len(by)})

    n = len(rows)
    zero = sum(1 for r in rows if r["ref_files"] == 0)
    out = {
        "尺": "含扫描器" if a.with_scanners else "剔除扫描器（严尺）",
        "语料文件数": len(texts),
        "分片总数": n,
        "零引用件数": zero,
        "零引用率": round(zero / max(1, n), 3),
        "被1件引用": sum(1 for r in rows if r["ref_files"] == 1),
        "被2-4件引用": sum(1 for r in rows if 2 <= r["ref_files"] <= 4),
        "被5件以上": sum(1 for r in rows if r["ref_files"] >= 5),
        "中位引用件数": statistics.median([r["ref_files"] for r in rows]),
        "零引用件": [r["file"] for r in rows if r["ref_files"] == 0],
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
