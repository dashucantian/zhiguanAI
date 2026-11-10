#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四条判据自测（只读真源；改动测试只动 _analysis_tmp 下的字节一致副本）。

判据（派工函 §二）：
  ① 图上每个节点都能点回一条登记件原文（文件加行号或章节锚）
  ② 改一条登记件、刷新后对应节点跟着变
  ③ validate-anchors 零空行锚、零越界
  ④ 故意改坏一个锚，探针能抓到（抓不到即真值闸失效）

用法：python selftest_four_criteria.py
输出：同目录 selftest_readings.txt（逐条读数＋实测耗时）。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIX = ROOT / "_analysis_tmp" / "field_fixture"
SRC_REL = {
    "identity": "01_项目管理/AI代理身份登记.md",
    "tasks": "01_项目管理/任务登记.md",
    "rulings": "01_项目管理/待裁单.md",
    "arch": "05_产品与开发/架构可视化/architecture-model.json",
}

sys.path.insert(0, str(HERE))
import build_field_model as B  # noqa: E402

READ = []


def emit(s=""):
    READ.append(s)
    print(s)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_validator(model_path: Path, root: Path | None = None):
    cmd = [sys.executable, str(HERE / "validate_anchors.py"), "--model", str(model_path)]
    if root:
        cmd += ["--root", str(root)]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.perf_counter() - t0
    return proc, dt


def main():
    t_all = time.perf_counter()
    emit("=" * 78)
    emit("关系场域二维活看板 · 四条判据自测")
    emit("实测时刻：" + datetime.now().astimezone().isoformat(timespec="seconds"))
    emit(f"Python：{sys.version.split()[0]}  根：{ROOT}")
    emit("=" * 78)

    # ── 判据 ③ 前置：真模型构建 + 探针 ──
    emit("")
    emit("【判据③】validate-anchors 零空行锚、零越界")
    t0 = time.perf_counter()
    model, jp, js = B.build(ROOT, HERE / "data")
    build_dt = time.perf_counter() - t0
    emit(f"  构建：{build_dt*1000:.0f} ms  版本 {model['version']}  生成 {model['generatedAt']}")
    emit(f"  读数：节点 {model['stats']['nodes']} / 边 {model['stats']['edges']} / 锚点 {model['stats']['anchors']}")
    for s in model["sources"]:
        emit(f"  源 {s['label']}：{s['lines']} 行 / {s['bytes']} 字节 / sha256 {s['sha256'][:16]}… / mtime {s['mtime']}")
    proc3, dt3 = run_validator(HERE / "data" / "field-model.json")
    emit(f"  探针耗时 {dt3*1000:.0f} ms  退出码 {proc3.returncode}")
    for line in proc3.stdout.strip().splitlines():
        emit("  " + line)
    if proc3.stderr.strip():
        emit("  stderr: " + proc3.stderr.strip()[:500])
    ok3 = proc3.returncode == 0 and "空行 0" in proc3.stdout and "越界 0" in proc3.stdout
    emit(f"  判据③：{'PASS' if ok3 else 'FAIL'}")

    # ── 判据 ① 机器部分：每个节点都有锚，且锚都能回读 ──
    emit("")
    emit("【判据①】图上每个节点都能点回一条登记件原文")
    nodes_no_anchor = [n["id"] for n in model["nodes"] if not n.get("anchors")]
    emit(f"  节点总数 {len(model['nodes'])}；有锚节点 {len(model['nodes']) - len(nodes_no_anchor)}；无锚 {len(nodes_no_anchor)}")
    if nodes_no_anchor:
        emit("  无锚节点：" + ", ".join(nodes_no_anchor[:20]))
    # 抽 8 个跨层节点，展示回源文件:行号
    picks = []
    for want in ["subject.human.fashi", "subject.window.W1", "subject.ai.AI-035",
                 "task.TASK-20261108-01", "boundary.ruling.relation-domain",
                 "boundary.window.W1", "model.hub", "model.node.actor.fashi"]:
        n = next((x for x in model["nodes"] if x["id"] == want), None)
        if n and n.get("anchors"):
            a = n["anchors"][0]
            picks.append((n["label"], a["file"], a["line"]))
    emit("  跨层抽样（节点 → 文件:行号）：")
    for label, f, ln in picks:
        emit(f"    {label} → {f}:{ln}")
    ok1 = not nodes_no_anchor and proc3.returncode == 0
    emit(f"  判据①（机器部分）：{'PASS' if ok1 else 'FAIL'}；页面点击回源另见浏览器实测")

    # ── 判据 ② 改一条登记件，刷新后节点跟着变（字节一致副本） ──
    emit("")
    emit("【判据②】改一条登记件、刷新后对应节点跟着变")
    emit("  做法：不碰共享在途件；把四源复制到 _analysis_tmp/field_fixture/src，先核副本与源件逐件 sha256 相同，")
    emit("        再改副本里的任务状态行，重建后比对节点；页面自动刷新另见浏览器实测。")
    if FIX.exists():
        shutil.rmtree(FIX)
    fx_src = FIX / "src"
    fx_out = FIX / "out"
    for rel in SRC_REL.values():
        dst = fx_src / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    same = all(sha(ROOT / rel) == sha(fx_src / rel) for rel in SRC_REL.values())
    emit(f"  副本与源件 sha256 全同：{same}")
    for rel in SRC_REL.values():
        emit(f"    {rel}: {sha(ROOT / rel)[:16]}… == {sha(fx_src / rel)[:16]}…")
    t0 = time.perf_counter()
    fx_model1, _, _ = B.build(fx_src, fx_out)
    fx_build1 = time.perf_counter() - t0
    n1 = next(n for n in fx_model1["nodes"] if n["id"] == "task.TASK-20261108-01")
    status1 = n1["status"]
    anchor1 = next(a for a in n1["anchors"] if a["note"] == "任务状态")
    v1 = fx_model1["version"]
    emit(f"  改前：版本 {v1}  状态 {status1}  锚行 {anchor1['line']}  原文 {anchor1['raw'][:80]}")
    # 只改副本任务件里的状态行（行数不变）
    tf = fx_src / SRC_REL["tasks"]
    lines = tf.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    target = None
    in_block = False
    for i, ln in enumerate(lines):
        if ln.strip() == "### TASK-20261108-01":
            in_block = True
            continue
        if in_block and ln.startswith("### "):
            break
        if in_block and ln.startswith("- 状态："):
            target = i
            break
    if target is None:
        raise SystemExit("副本里找不到 TASK-20261108-01 的状态行")
    old_line = lines[target]
    lines[target] = "- 状态：**自测改动态**（判据②：改一条登记件后节点跟着变；原状态进行中）"
    tf.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    emit(f"  改动行：{SRC_REL['tasks']}:{target+1}")
    emit(f"    旧：{old_line[:100]}")
    emit(f"    新：{lines[target][:100]}")
    t0 = time.perf_counter()
    fx_model2, _, _ = B.build(fx_src, fx_out)
    fx_build2 = time.perf_counter() - t0
    n2 = next(n for n in fx_model2["nodes"] if n["id"] == "task.TASK-20261108-01")
    status2 = n2["status"]
    anchor2 = next(a for a in n2["anchors"] if a["note"] == "任务状态")
    v2 = fx_model2["version"]
    emit(f"  改后：版本 {v2}  状态 {status2}  锚行 {anchor2['line']}  原文 {anchor2['raw'][:80]}")
    version_changed = v1 != v2
    status_changed = status1 != status2 and "自测改动态" in status2
    anchor_changed = anchor1["raw"] != anchor2["raw"]
    emit(f"  版本变化 {version_changed}；状态变化 {status_changed}；锚原文变化 {anchor_changed}")
    ok2 = same and version_changed and status_changed and anchor_changed
    emit(f"  判据②（数据层）：{'PASS' if ok2 else 'FAIL'}")

    # ── 判据 ④ 故意改坏一个锚，探针能抓到 ──
    emit("")
    emit("【判据④】故意改坏一个锚，探针能抓到")
    real_model = HERE / "data" / "field-model.json"
    base = json.loads(real_model.read_text(encoding="utf-8"))
    # 找任务件里的第一处空行，作为「空行锚」坏法
    tf_lines = (ROOT / SRC_REL["tasks"]).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blank_line = next((i + 1 for i, ln in enumerate(tf_lines) if i > 0 and ln.strip() == ""), 1)
    cases = []
    # 坏法 A：空行锚
    m = json.loads(json.dumps(base, ensure_ascii=False))
    victim = next(n for n in m["nodes"] if n["id"] == "task.TASK-20261108-01")
    victim["anchors"][1]["line"] = blank_line
    cases.append(("空行锚", m, "blank"))
    # 坏法 B：越界
    m = json.loads(json.dumps(base, ensure_ascii=False))
    victim = next(n for n in m["nodes"] if n["id"] == "task.TASK-20261108-01")
    victim["anchors"][1]["line"] = 999999
    cases.append(("越界锚", m, "out_of_range"))
    # 坏法 C：指纹不符
    m = json.loads(json.dumps(base, ensure_ascii=False))
    victim = next(n for n in m["nodes"] if n["id"] == "task.TASK-20261108-01")
    victim["anchors"][1]["fp"] = "不存在的指纹XYZ"
    cases.append(("指纹不符", m, "fingerprint_mismatch"))
    results = []
    for name, mm, want in cases:
        bp = FIX / f"broken_{want}.json"
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps(mm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        proc, dt = run_validator(bp)
        fail_line = next((l for l in proc.stdout.splitlines() if "[FAIL]" in l), "")
        hit = proc.returncode == 1 and want in proc.stdout
        results.append((name, want, proc.returncode, hit, fail_line, dt))
        emit(f"  {name}：退出码 {proc.returncode}  命中 {want}：{hit}")
        if fail_line:
            emit("    " + fail_line.strip())
    # 阴性对照：未改坏的真模型必须 CLEAN
    proc_neg, _ = run_validator(real_model)
    emit(f"  阴性对照（真模型）：退出码 {proc_neg.returncode}（应为 0）")
    ok4 = all(hit for _, _, _, hit, _, _ in results) and proc_neg.returncode == 0
    emit(f"  判据④：{'PASS' if ok4 else 'FAIL'}")

    # ── 汇总与耗时 ──
    total_dt = time.perf_counter() - t_all
    emit("")
    emit("=" * 78)
    emit("汇总")
    emit(f"  判据①：{'PASS' if ok1 else 'FAIL'}（{len(model['nodes'])} 节点全部有锚；锚点探针 CLEAN）")
    emit(f"  判据②：{'PASS' if ok2 else 'FAIL'}（副本 sha 全同={same}；版本 {v1}→{v2}；状态 {status1}→{status2}）")
    emit(f"  判据③：{'PASS' if ok3 else 'FAIL'}（空行 {0 if ok3 else '见上'}／越界 {0 if ok3 else '见上'}）")
    emit(f"  判据④：{'PASS' if ok4 else 'FAIL'}（三种坏法全部报红，阴性对照 CLEAN）")
    emit("  实测耗时：")
    emit(f"    真模型构建 {build_dt*1000:.0f} ms；探针 {dt3*1000:.0f} ms")
    emit(f"    副本构建 {fx_build1*1000:.0f} ms / 改后重建 {fx_build2*1000:.0f} ms")
    emit(f"    自测总耗时 {total_dt*1000:.0f} ms（{total_dt:.2f} 秒）")
    emit("  据实说明：")
    emit("    · 判据②的改件测试在字节一致副本上做，未改任何共享在途登记件；副本 sha256 已逐件对上。")
    emit("    · 判据①的页面点击部分与判据②的页面刷新部分另由浏览器实测留读数。")
    emit("    · 判据④的坏锚只改模型副本，不动源件与真模型。")
    emit("=" * 78)
    (HERE / "selftest_readings.txt").write_text("\n".join(READ) + "\n", encoding="utf-8", newline="\n")
    print("READINGS ->", HERE / "selftest_readings.txt")
    sys.exit(0 if (ok1 and ok2 and ok3 and ok4) else 1)


if __name__ == "__main__":
    main()