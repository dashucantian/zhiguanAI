#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261010_W1_manifest_pairing_final.py — 24 坐 ↔ manifest 配对与 participant_id 终查

前两件的错各一处，本件一并纠正：
  ① xcheck 把「读不进」的异常串当非空 ⇒ 23 坐被误计为「有值」（分类逻辑缺陷）；
  ② diag 只按 `<npz 同名>.session_manifest.json` 找配对 ⇒ 归档位实际叫
     `session_manifest.json`（无前缀），于是 9 坐被误报「无同名 manifest」。
⇒ 本件不靠文件命名约定，改按 **manifest 自报的 `session_id`／`files` 字段** 配对，
   并对每件做编码阶梯（utf-8-sig→utf-8→gbk→cp936→utf-16），失败时留字节证据。
仍全程只读。
"""
import hashlib
import json
import os
import sys
from collections import Counter

ROOT = r"D:\Project\zhiguanAI"
sys.path.insert(0, ROOT)
import congci_pipeline as cp  # noqa: E402

LADDER = ("utf-8-sig", "utf-8", "gbk", "cp936", "utf-16", "utf-16-le")


def ladder(path):
    raw = open(path, "rb").read()
    tries = []
    for enc in LADDER:
        try:
            obj = json.loads(raw.decode(enc))
            return obj, enc, raw, tries
        except Exception as e:
            tries.append(f"{enc}:{type(e).__name__}"
                         + (f"@{e.start}" if isinstance(e, UnicodeDecodeError) else ""))
    return None, None, raw, tries


def idx_by_field(base_dir):
    """把目录内所有 manifest 按其内部 session_id 与 files 引用建索引（不靠文件名）。"""
    by_sid, by_file, names = {}, {}, []
    for f in sorted(os.listdir(base_dir)):
        if not f.endswith(".session_manifest.json") and f != "session_manifest.json":
            continue
        p = os.path.join(base_dir, f)
        obj, enc, raw, tries = ladder(p)
        names.append((f, enc, tries[-1] if enc is None else ""))
        if not isinstance(obj, dict):
            continue
        sid = obj.get("session_id")
        if sid:
            by_sid.setdefault(str(sid), []).append((p, obj, enc))
        for ref in (obj.get("files") or []):
            if isinstance(ref, str):
                by_file.setdefault(os.path.basename(ref), []).append((p, obj, enc))
        for k in ("eeg_file", "npz", "raw_file", "data_file"):
            v = obj.get(k)
            if isinstance(v, str):
                by_file.setdefault(os.path.basename(v), []).append((p, obj, enc))
    return by_sid, by_file, names


doc = json.load(open(cp.index_path(), "r", encoding="utf-8-sig"))
rows = doc["rows"] if isinstance(doc, dict) else doc

print("=== 一、归档位 9 坐：02_raw/<sid>/session_manifest.json 直读 ===")
arch = [r for r in rows if (r.get("qc_source") or "").startswith("03_quality")]
cat = Counter()
for r in arch:
    npz = r.get("npz_resolved") or r.get("npz_path") or ""
    d = os.path.dirname(os.path.abspath(npz))
    p = os.path.join(d, "session_manifest.json")
    if not os.path.exists(p):
        cat["目录内无 session_manifest.json"] += 1
        print(f"  {os.path.basename(d):26s} 无该件")
        continue
    obj, enc, raw, tries = ladder(p)
    if obj is None:
        cat["全编码读不进"] += 1
        print(f"  {os.path.basename(d):26s} 读不进 {tries} 头字节={raw[:8]!r}")
        continue
    pid = obj.get("participant_id")
    sid_m = obj.get("session_id")
    same = (str(sid_m) == os.path.basename(d))
    cat[f"pid={'非空' if pid not in (None,'') else '空/缺'}"] += 1
    print(f"  {os.path.basename(d):26s} enc={enc:9s} pid={pid!r:8s} "
          f"manifest.session_id={sid_m!r} 与目录名一致={same}")

print("\n=== 二、暂存位 15 坐：按 manifest 内部字段配对（report 目录）===")
rep = os.path.join(ROOT, "muse2-repo", "muse2-master", "report")
by_sid, by_file, names = idx_by_field(rep)
n_man = len(names)
bad = [q for q in names if q[1] is None]
print(f"[report 目录] manifest 件数={n_man} 全编码读不进={len(bad)}")
if bad:
    for q in bad[:5]:
        print(f"    {q[0]} ← {q[2]}")
stg = [r for r in rows if (r.get("qc_source") or "") == "assess_cached"]
for r in stg:
    npz = r.get("npz_resolved") or r.get("npz_path") or ""
    base = os.path.basename(npz)
    hits = by_file.get(base, [])
    if not hits:
        # 退一步：按 manifest 的 session_id 与本 npz 的时间戳段对
        ts = base.replace("local_", "").replace(".partial.npz", "").replace(".npz", "")
        alt = [(p, o, e) for sid, lst in by_sid.items() for (p, o, e) in lst
               if ts in str(sid)]
        hits = alt
        how = f"按 session_id 含时间戳 {ts}"
    else:
        how = "按 files 引用命中"
    if not hits:
        cat_2 = "无任一 manifest 引用本 npz"
        pids = None
    else:
        pids = sorted({repr(o.get("participant_id")) for _, o, _ in hits})
        cat_2 = f"命中 {len(hits)} 件"
    cat[("暂存", cat_2)] += 1
    print(f"  {base:32s} {how:26s} → {cat_2} pid集合={pids}")

print("\n=== 三、汇总 ===")
for k, v in sorted(cat.items(), key=lambda x: str(x[0])):
    print(f"  {str(k):52s} {v}")

print("\n=== 四、report 目录里 manifest 的 pid 全值分布（不靠索引，独立复算）===")
c = Counter()
for f, enc, err in names:
    if enc is None:
        c["<读不进>"] += 1
        continue
    p = os.path.join(rep, f)
    obj, _, _, _ = ladder(p)
    c[repr(obj.get("participant_id"))] += 1
print(f"  {dict(c)}")

print("\n=== 五、真实持久脑 sha16（未喂脑自证）===")
bp = cp.brain_path()
print(f"  size={os.path.getsize(bp)} sha16="
      f"{hashlib.sha256(open(bp,'rb').read()).hexdigest()[:16]}"
      f"（现势应为 199aafe7414a0b75）")
print("\n[零写入自证] 只 open(...,'rb'/'r')＋os.listdir；未写、未取锁、未调 enqueue／assess_cached。")
