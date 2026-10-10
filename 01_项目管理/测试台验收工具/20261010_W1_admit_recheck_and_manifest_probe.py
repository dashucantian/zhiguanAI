#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261010_W1_admit_recheck_and_manifest_probe.py — 两件只读点检

W3 派工函（20261009-W3-AI014-派工W1_正源钉定与②④准修_批B解禁.md）§三 末行要求
「留实测证据（隔离位 5 会话 admit() 应变 False）」，§八#4 另请补查
「local_*.session_manifest.json 里有无 participant 字段」。

本件办这两件，且**刻意不调用会回落 assess_cached 的那条路**：
`_qc_verdict` 在定稿探针扑空时会落 `qc_pipeline.assess_cached(npz)`，而该函数
**会写 `.qc_cache`**（法师 2026-10-09 裁「丙已否」＝不得把这条写副作用请进
判定链）。⇒ 先自行做只读探针，只在**定稿确实存在**的会话上调 admit()。

纪律：零写入／零取锁／零入队／零喂脑／不出网／不读任何波形数值（只读 qc.json
与 manifest 的键名与少量标量）；目录列举一律有界单层，禁从项目根无差别递归。
"""
import json
import os
import sys

ROOT = r"D:\Project\zhiguanAI"
sys.path.insert(0, ROOT)

import congci_pipeline as cp  # noqa: E402

ZEN = cp._CFG["zen_root"]
print(f"[取值式] cp._CFG['zen_root'] = {ZEN}")
print(f"[取值式] cp.brain_path()     = {cp.brain_path()}")
print(f"[取值式] cp.index_path()     = {cp.index_path()}")
print()


def probe_fixed_qc(npz_path):
    """复刻 _qc_verdict 的定稿探针（纯读），返回 (命中路径或 None, sid)。"""
    d = os.path.dirname(os.path.abspath(npz_path))
    if not os.path.basename(d).startswith("ZEN-"):
        return None, None
    sid = os.path.basename(d)
    for cand in (os.path.normpath(os.path.join(d, "..", "..",
                                               "03_quality_control", sid, "qc.json")),
                 os.path.join(d, "qc.json")):
        if os.path.exists(cand):
            return cand, sid
    return None, sid


print("=== 一、隔离位会话 admit() 复测（只在定稿在场时调，避开 assess_cached 写）===")
qroot = os.path.join(ZEN, "03_quality_control", "quarantine")
print(f"[目录] {qroot}  存在={os.path.isdir(qroot)}")
if os.path.isdir(qroot):
    sids = sorted(q for q in os.listdir(qroot)
                  if os.path.isdir(os.path.join(qroot, q)))
    print(f"[计数] 隔离位子目录 {len(sids)} 个")
    n_admit_true = 0
    for sid in sids:
        d = os.path.join(qroot, sid)
        npzs = sorted(f for f in os.listdir(d) if f.endswith(".npz")
                      and not f.endswith(".partial.npz"))
        part = [f for f in os.listdir(d) if f.endswith(".partial.npz")]
        target = os.path.join(d, npzs[0]) if npzs else (
            os.path.join(d, part[0]) if part else None)
        if target is None:
            print(f"  {sid}: <目录内无 npz，文件={sorted(os.listdir(d))[:6]}>")
            continue
        hit, _ = probe_fixed_qc(target)
        if hit is None:
            print(f"  {sid}: 定稿探针扑空 ⇒ **跳过 admit()**"
                  f"（会落 assess_cached 写 .qc_cache＝丙已否，不触发）")
            continue
        with open(hit, "r", encoding="utf-8") as f:
            q = json.load(f)
        res = cp.admit(target)          # 不带 qc ⇒ 走定稿探针，与生产同路
        ad = res.get("admitted")
        n_admit_true += 1 if ad else 0
        print(f"  {sid}: 定稿={os.path.relpath(hit, ZEN)} "
              f"recommend={q.get('recommend')!r} "
              f"quarantined={q.get('quarantined')!r} "
              f"=> admit()={ad!r} reason={(res.get('reason') or '')[:44]!r}")
    print(f"[小结] 隔离位 admit()==True 的会话数 = {n_admit_true}"
          f"／{len(sids)}（W3 §三 的期望值＝0）")
print()

print("=== 二、local_*.session_manifest.json 有无 participant 字段（W3 §八#4）===")
cands = []
for base in (os.path.join(ROOT, "muse2-repo", "muse2-master", "report"),
             os.path.join(ZEN, "02_raw"),
             os.path.join(ZEN, "00_intake")):
    print(f"[找] {base}  存在={os.path.isdir(base)}")
    if not os.path.isdir(base):
        continue
    for f in sorted(os.listdir(base)):
        if f.endswith(".session_manifest.json"):
            cands.append(os.path.join(base, f))
print(f"[计数] 命中 manifest 件数 = {len(cands)}")
KEYS = None
for p in cands[:6]:
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            m = json.load(f)
    except Exception as e:
        print(f"  {os.path.basename(p)}: 读不进 {type(e).__name__}: {e}")
        continue
    if not isinstance(m, dict):
        print(f"  {os.path.basename(p)}: 顶层非 dict（{type(m).__name__}）")
        continue
    ks = sorted(m.keys())
    if KEYS is None:
        KEYS = ks
    hits = [k for k in ks if "particip" in k.lower() or k.lower() in ("pid", "subject", "user")]
    vals = {k: (str(m.get(k))[:12] if m.get(k) is not None else None) for k in hits}
    print(f"  {os.path.basename(p)}: keys={ks}")
    print(f"      participant 类键＝{hits} 值＝{vals}")
if KEYS is not None:
    print(f"[小结] 首件 manifest 的键集＝{KEYS}")
    print(f"[小结] 含 participant 类键＝{any('particip' in k.lower() for k in KEYS)}")
print()

print("=== 三、01_registry 现势（有界单层，为核「正源钉定」后的读写面）===")
reg = os.path.join(ZEN, "01_registry")
if os.path.isdir(reg):
    for f in sorted(os.listdir(reg)):
        fp = os.path.join(reg, f)
        if os.path.isfile(fp):
            print(f"  {f:34s} {os.path.getsize(fp):6d} B  mtime="
                  f"{__import__('time').strftime('%Y-%m-%d %H:%M', __import__('time').localtime(os.path.getmtime(fp)))}")
        else:
            print(f"  {f:34s} <dir>")
print()
print("=== 四、participant_status.json 是否已由谁建出（撤回真值源 JSON 侧）===")
psj = os.path.join(ZEN, "00_governance", "participant_status.json")
print(f"  {psj}  存在={os.path.exists(psj)}")
gov = os.path.join(ZEN, "00_governance")
if os.path.isdir(gov):
    print(f"  00_governance 内容＝{sorted(os.listdir(gov))}")
print("\n[零写入自证] 本脚本只 os.path.exists／os.listdir／open(...,'r')；"
      "未 open 任何件为写、未取任何锁、未调 enqueue／_commit_row／assess_cached。")
