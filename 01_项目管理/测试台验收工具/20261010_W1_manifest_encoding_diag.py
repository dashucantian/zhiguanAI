#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261010_W1_manifest_encoding_diag.py — 上件把「读不进」误计为「有值」，此处按字节查因

上一件（xcheck）的键分类写成 `pid not in (None,'')`，而 pid 在我自己构造的异常
字符串里 ⇒ **14＋9＝23 坐的「读不进」被算成「有值」**。那是我这个诊断脚本的缺陷，
不是数据的缺陷。本件逐字节查清：编码是什么、失败在哪一字节、换编码能不能读到
participant_id。仍全程只读。
"""
import json
import os
import sys
from collections import Counter

ROOT = r"D:\Project\zhiguanAI"
sys.path.insert(0, ROOT)
import congci_pipeline as cp  # noqa: E402

ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "cp936", "utf-16", "latin-1")


def probe(path):
    raw = open(path, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    out = []
    for enc in ENCODINGS:
        try:
            txt = raw.decode(enc)
        except Exception as e:
            out.append((enc, f"FAIL {type(e).__name__}@{getattr(e, 'start', '?')}"))
            continue
        try:
            m = json.loads(txt)
            out.append((enc, f"OK keys={len(m) if isinstance(m, dict) else '-'} "
                             f"pid={m.get('participant_id')!r}"
                             if isinstance(m, dict) else (enc, f"OK 非dict {type(m).__name__}")))
        except Exception as e:
            out.append((enc, f"DECODE_OK 但 JSON 败 {type(e).__name__}"))
    return raw, bom, out


doc = json.load(open(cp.index_path(), "r", encoding="utf-8-sig"))
rows = doc["rows"] if isinstance(doc, dict) else doc

print("=== 一、归档 9 坐：npz 同目录到底有什么文件（列两个样本，有界单层）===")
arch = [r for r in rows if (r.get("qc_source") or "").startswith("03_quality")]
for r in arch[:2]:
    npz = r.get("npz_resolved") or r.get("npz_path")
    d = os.path.dirname(os.path.abspath(npz))
    print(f"  npz={npz}")
    print(f"    目录内容={sorted(os.listdir(d)) if os.path.isdir(d) else '<目录不存在>'}")

print("\n=== 二、暂存 15 坐：npz 是否真在 report 目录（列首个）===")
stg = [r for r in rows if (r.get("qc_source") or "") == "assess_cached"]
for r in stg[:2]:
    npz = r.get("npz_resolved") or r.get("npz_path")
    d = os.path.dirname(os.path.abspath(npz))
    ms = sorted(f for f in os.listdir(d) if f.endswith(".session_manifest.json")) \
        if os.path.isdir(d) else None
    print(f"  npz={npz}")
    print(f"    该目录 manifest 件数={len(ms) if ms is not None else '<目录不存在>'} 前 6＝{(ms or [])[:6]}")

print("\n=== 三、逐坐编码诊断（关键：换编码后 participant_id 到底读不读得到）===")
cat = Counter()
detail = []
for r in rows:
    npz = r.get("npz_resolved") or r.get("npz_path") or ""
    d = os.path.dirname(os.path.abspath(npz))
    base = os.path.basename(npz)
    cand = os.path.join(d, base.replace(".partial.npz", ".npz").replace(
        ".npz", ".session_manifest.json"))
    if not os.path.exists(cand):
        cat["无同名 manifest"] += 1
        detail.append((r.get("qc_source"), base, "无同名 manifest", None, None))
        continue
    raw, bom, out = probe(cand)
    got = None
    for enc, res in out:
        if isinstance(res, str) and res.startswith("OK "):
            got = (enc, res)
            break
    if got:
        pid = None
        try:
            pid = json.loads(raw.decode(got[0])).get("participant_id")
        except Exception:
            pass
        tag = f"可读({got[0]})|pid={'非空' if (pid not in (None,'')) else '空/缺'}"
    else:
        first = out[0][1] if out and isinstance(out[0][1], str) else "?"
        tag = f"六种编码全读不进|首因={first.split('@')[0]}"
        pid = None
    cat[tag] += 1
    detail.append((r.get("qc_source"), base, tag, bom, pid))

for k, v in sorted(cat.items()):
    print(f"  {k:46s} {v}")

print("\n=== 四、每坐明细（脱敏＝只报代号，不报姓名）===")
for src, base, tag, bom, pid in sorted(detail, key=lambda x: (str(x[0]), x[1])):
    print(f"  {str(src)[:30]:30s} {base[:30]:30s} BOM={bom} pid={pid!r} → {tag}")

print("\n=== 五、真实持久脑 sha16（确认本批全程未喂脑·只读自证）===")
import hashlib
bp = cp.brain_path()
print(f"  {bp}\n  size={os.path.getsize(bp)} sha16="
      f"{hashlib.sha256(open(bp,'rb').read()).hexdigest()[:16]}")
print("\n[零写入自证] 只 open(...,'rb')＋os.listdir；未写、未取锁、未调 enqueue／assess_cached。")
