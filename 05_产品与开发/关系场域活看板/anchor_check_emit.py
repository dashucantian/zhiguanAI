#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锚体检跑批发射器（薄格式化器）。

只读运行同目录 validate_anchors.py --show-ok，解析其逐条行与摘要行，
重排为 data/anchor-check.js（window.ANCHOR_CHECK，注入式同 field-model.js）。
硬约束：①不复制任何一条锚判据，只做解析＋重排；②解析行数 ≠ 探针自报锚数
⇒ 不写文件、退码非零、两个数都打印；③只写 data/anchor-check.js 一个出口；
④零出网、零第三方库、纯 stdlib。
"""
from __future__ import annotations

import argparse
import ast
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "anchor-check.js"

LINE_RE = re.compile(r"^节点\s+(\d+)\s*/\s*边\s+(\d+)\s*/\s*锚点\s+(\d+)$")
COUNT_RE = re.compile(r"^OK\s+(\d+)\s+空行\s+(\d+)\s+越界\s+(\d+)\s+缺文件\s+(\d+)\s+指纹不符\s+(\d+)$")
OK_RE = re.compile(r"^\[OK\]\s+(\S+)\s+(\S+)\s+(\S+?):(\d+)$")
FAIL_RE = re.compile(r"^\[FAIL\]\s+(\S+)\s+(\S+)\s+(\S+?):(\d+)\s+(\S+)\s+(.*?)\s+fp=(.+)$")


def run_probe(model: str, root: str):
    cmd = [sys.executable, str(HERE / "validate_anchors.py"), "--show-ok"]
    if model:
        cmd += ["--model", model]
    if root:
        cmd += ["--root", root]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(cmd, capture_output=True, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def unrepr(s: str) -> str:
    s = s.strip()
    try:
        v = ast.literal_eval(s)
        return v if isinstance(v, str) else s
    except Exception:
        return s.strip("'\"")


def parse(text: str):
    rows, ok_rows = [], 0
    summary, version = {}, ""
    for raw in text.splitlines():
        st = raw.strip()
        m = LINE_RE.match(st)
        if m:
            summary["nodes"], summary["edges"], summary["anchors"] = (int(x) for x in m.groups())
            continue
        if st.startswith("版本："):
            rest = st[len("版本："):].split()
            version = rest[0] if rest else ""
            continue
        m = COUNT_RE.match(st)
        if m:
            (summary["ok"], summary["blank"], summary["out_of_range"],
             summary["missing_file"], summary["fingerprint_mismatch"]) = (int(x) for x in m.groups())
            continue
        m = OK_RE.match(st)
        if m:
            ok_rows += 1
            continue
        m = FAIL_RE.match(st)
        if m:
            kind, owner, file, line, status, reason, right = m.groups()
            fp_repr, _, actual_repr = right.partition("  actual=")
            rows.append({
                "kind": kind, "owner": owner, "file": file, "line": int(line),
                "status": status, "reason": reason,
                "fp": unrepr(fp_repr), "actual": unrepr(actual_repr),
            })
            continue
    return rows, ok_rows, summary, version


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="")
    ap.add_argument("--root", default="")
    args = ap.parse_args()

    rc, text = run_probe(args.model, args.root)
    bad, ok_rows, summary, version = parse(text)
    claimed = summary.get("anchors")
    parsed = ok_rows + len(bad)
    if claimed is None or parsed != claimed or ok_rows != summary.get("ok"):
        print("拒发：探针自报锚数=%s 解析行数=%s（OK %s / FAIL %s）不符"
              % (claimed, parsed, ok_rows, len(bad)))
        return 2

    payload = {
        "probeExit": rc,
        "clean": ("CLEAN" in text),
        "version": version,
        "checkedAtLocal": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "okCount": ok_rows,
        "bad": bad,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.ANCHOR_CHECK = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    OUT.write_bytes(js.encode("utf-8"))
    print("已写 %s：锚 %s、OK %s、坏 %s（缺文件 %s／空行 %s／越界 %s／指纹不符 %s）、探针退码 %s"
          % (OUT, claimed, ok_rows, len(bad), summary.get("missing_file", 0),
             summary.get("blank", 0), summary.get("out_of_range", 0),
             summary.get("fingerprint_mismatch", 0), rc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
