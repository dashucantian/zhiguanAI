#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261010_W1_manifest_participant_xcheck.py — 已喂 24 坐逐坐对表 manifest 的 participant_id

缘起：20261010 探针实测 `local_*.session_manifest.json` **带 `participant_id` 键**
⇒ 本窗 20261009 盘查件 §4.2「暂存 15 坐任何地方都没有逐坐归属」那条**被证伪**，
须逐坐实测重出（不能只看 6 个抽样就宣称 15 坐都有／都没有）。

本件只读：读索引（cp.index_path() 取值式）＋逐坐 npz 同目录找 manifest＋读其
participant_id。**不读任何波形数值、不写、不取锁、不出网。**

====================================================================
⛔ 本件的**汇总数作废**，请勿引用（〔2026-10-10 自曝更正〕，代码本身故意保留原样
   以便复现当时那次错）：
   缺陷在分类那一行 `pid not in (None, "")`——读失败时我把 `pid` 赋成了**自己构造
   的异常字符串**，该字符串当然"非空"，于是 22 坐的「读不进」被计成「有值」，
   输出里的「23/24 有值」是一个**假阳性汇总**。
   另有第二处错：本件与同日的 encoding_diag 都按 `<npz 同名>.session_manifest.json`
   找配对，而归档位真名是 `session_manifest.json`（无前缀）⇒ 归档 9 坐被误报配对失败。
   ⇒ 权威结果见 `20261010_W1_manifest_pairing_final.py`（改按 manifest 内部
   `session_id`／`files` 字段配对＋六编码阶梯）：归档 9/9 可读且全 P001；
   暂存 15 坐＝13 无 manifest ＋ 2 有（一 P001 一空串）；report 目录 33 件填充率
   63.6%（P001×21／空串×12）。教训已写进当日回执 §3.3：**配对不得靠文件命名约定**。
====================================================================
"""
import json
import os
import sys
from collections import Counter

ROOT = r"D:\Project\zhiguanAI"
sys.path.insert(0, ROOT)
import congci_pipeline as cp  # noqa: E402

doc = json.load(open(cp.index_path(), "r", encoding="utf-8-sig"))
rows = doc["rows"] if isinstance(doc, dict) else doc
print(f"[取值式] cp.index_path() = {cp.index_path()}")
print(f"[计数] 索引行数 = {len(rows)}")


def find_manifest(npz_path):
    """npz 同目录找配对 manifest：先按同名前缀，再退到目录内任一 *.session_manifest.json。"""
    d = os.path.dirname(os.path.abspath(npz_path))
    stem = os.path.basename(npz_path)
    for cand in (stem.replace(".npz", ".session_manifest.json"),
                 stem.replace(".partial.npz", ".session_manifest.json")):
        p = os.path.join(d, cand)
        if os.path.exists(p):
            return p, "同名配对"
    if not os.path.isdir(d):
        return None, "目录不存在"
    hits = sorted(f for f in os.listdir(d) if f.endswith(".session_manifest.json"))
    if len(hits) == 1:
        return os.path.join(d, hits[0]), "目录内唯一"
    if len(hits) > 1:
        return None, f"目录内多件({len(hits)})不可唯一配对"
    return None, "目录内无 manifest"


print("\n=== 逐坐对表（按 qc_source 分组，与盘查件 §4.2 的两类划分对齐）===")
stat = Counter()
buckets = {}
for r in sorted(rows, key=lambda x: (x.get("qc_source") or "",
                                     x.get("npz_resolved") or x.get("npz_path") or "")):
    src = r.get("qc_source") or "(空)"
    npz = r.get("npz_resolved") or r.get("npz_path") or ""
    mp, how = find_manifest(npz)
    pid = None
    if mp:
        try:
            m = json.load(open(mp, "r", encoding="utf-8-sig"))
            pid = m.get("participant_id")
        except Exception as e:
            pid = f"<读不进 {type(e).__name__}>"
    key = f"{how}|{'有值' if (pid not in (None, '')) else ('空串' if pid == '' else '无')}"
    stat[key] += 1
    buckets.setdefault(src, []).append((
        os.path.basename(npz)[:34], (r.get("session_key") or "")[:18], key, pid))

for src, items in buckets.items():
    print(f"\n--- qc_source={src}（{len(items)} 坐）---")
    for name, sk, key, pid in items:
        print(f"  {name:34s} key={sk:18s} {key:24s} pid={pid!r}")

print("\n=== 汇总 ===")
for k, v in sorted(stat.items()):
    print(f"  {k:40s} {v}")
n_ok = sum(v for k, v in stat.items() if "|有值" in k)
print(f"[小结] 24 坐中「manifest 可唯一配对且 participant_id 非空」＝{n_ok}/{len(rows)}")
print(f"[小结] 「无 manifest 可配对」＝{sum(v for k, v in stat.items() if k.startswith('目录内无') or k.startswith('目录不存在') or k.startswith('目录内多件'))}")

print("\n=== 附：report 目录 33 件 manifest 的 participant_id 全值分布（脱敏＝只报代号）===")
rep = os.path.join(ROOT, "muse2-repo", "muse2-master", "report")
c = Counter()
nokey = 0
for f in sorted(os.listdir(rep)):
    if not f.endswith(".session_manifest.json"):
        continue
    try:
        m = json.load(open(os.path.join(rep, f), "r", encoding="utf-8-sig"))
    except Exception:
        c["<读不进>"] += 1
        continue
    if "participant_id" not in m:
        nokey += 1
    else:
        v = m.get("participant_id")
        c[repr(v)] += 1
print(f"  participant_id 值分布 = {dict(c)}")
print(f"  无该键的件数 = {nokey}")
print("\n[零写入自证] 只 open(...,'r')＋os.listdir；未写、未取锁、未调 enqueue／assess_cached。")
