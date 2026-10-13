# -*- coding: utf-8 -*-
"""证据台账自检（第一条·只读，不改任何文件）。

治的是什么形：文书里写"命中 0／全库没有／剩余 14 项"这类**数**，但读者无法知道它是量出来的还是减出来的、
取法是什么。台账把每条数钉成一行（测于／断言／取法／排除面／落在），文书里用一个号引它：

    本窗现读源表 80 行（ev:EV-0002）

本脚本查三件事，缺一报一行：
  甲 引了不存在的号（假引用）
  乙 号对、但那条台账缺 测于／取法／排除面 任一键（空心引用）
  丙 出现"数值零计数型断言"却既没带取法标记、也没引 ev 号（＝裸数）

判据不自己另抄一份：零计数正则与取法词表**从 收口检查.ps1 现读**（与诱饵集同一手法），
脚本改了判据，本自检立刻跟着变——不然是两套口径互相打架。

用法：
  python 01_项目管理/语料工程/ev_check.py --staged      # 查已 add 未提交的文件（pre-commit 用）
  python 01_项目管理/语料工程/ev_check.py --file 路径    # 查单个文件
  python 01_项目管理/语料工程/ev_check.py --dir 目录     # 查目录下全部 .md/.txt
退码：默认恒 0（提示型，绝不拦任何窗的提交）；加 --strict 才在有问题时退 1。
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

GATE = "收口检查.ps1"
LEDGER = os.path.join("01_项目管理", "语料工程", "证据台账.jsonl")
REF = re.compile(r"ev[:：]\s*(EV-\d{4})")
SKIP_NAMES = {"证据台账.jsonl"}
# 取证面自宣：本脚本只读，不写任何文件；检索面＝显式传入的 --staged/--file/--dir，不做全库扫（防坑 047 自产件污染）


def grab_from_gate():
    """从闸门源文件现读两条判据；读不到就返回 None，让调用方报'不可信'而不是静默通过。"""
    try:
        src = io.open(GATE, encoding="utf-8", errors="replace").read()
    except Exception as e:
        # ⚠不许让它崩：崩了又恰好在钩子里被 2>/dev/null 吞掉＝静默空操作（10-14 自证当场抓到这一形）
        print("[ev] ⚠读不到闸门源 %s：%s ⇒ 不作通过结论" % (GATE, type(e).__name__))
        return None, None
    m1 = re.search(r"\$re14\s*=\s*'([^']+)'", src)
    m2 = re.search(r"\$ok14\s*=\s*'([^']+)'", src)
    return (m1.group(1) if m1 else None), (m2.group(1) if m2 else None)


def load_ledger(path=None):
    path = path or LEDGER
    if not os.path.isfile(path):
        return None
    out = {}
    for ln in io.open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        d = json.loads(ln)
        out[d.get("id")] = d
    return out


def targets(a):
    if a.file:
        return [a.file]
    if a.dir:
        got = []
        for root, dirs, files in os.walk(a.dir):
            dirs[:] = [d for d in dirs if d not in (".git", "_analysis_tmp", "output", "node_modules", "__pycache__")]
            for f in files:
                if f.endswith((".md", ".txt")) and f not in SKIP_NAMES:
                    got.append(os.path.join(root, f))
        return got
    if a.staged:
        # -z ＋ quotepath=off：git 缺省把非 ASCII 路径转义成 "\346\265..." 并加引号，
        # 按换行切再判 endswith('.md') ⇒ 本仓中文名文书**全部落空**＝自检静默空转（10-14 自证抓到）。
        p = subprocess.run(["git", "-c", "core.quotepath=off", "diff", "--cached",
                            "--name-only", "--diff-filter=ACMR", "-z"],
                           capture_output=True)
        got = []
        for ln in p.stdout.decode("utf-8", "replace").split("\0"):
            ln = ln.strip()
            if ln.endswith((".md", ".txt")) and os.path.isfile(ln) and ln not in SKIP_NAMES:
                got.append(ln)
        return got
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--dir")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--ledger", help="换一份台账跑（自证乙形用；缺省＝证据台账.jsonl）")
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    rx_zero, rx_ok = grab_from_gate()
    led = load_ledger(a.ledger)
    if rx_zero is None or rx_ok is None:
        print("[ev] ⚠抠不到闸门判据（%s 可能已改形）⇒ 本自检不可信，不作通过结论" % GATE)
        return 1 if a.strict else 0
    if led is None:
        print("[ev] ⚠台账不存在（%s）⇒ 裸数无从绑证，本自检不可信" % LEDGER)
        return 1 if a.strict else 0
    okwords = [w for w in rx_ok.split("|") if w]

    fs = targets(a)
    if not fs:
        print("[ev] 检索面内 0 份文书（取法＝git diff --cached 的 .md/.txt；空面≠通过，只是本轮无对象）")
        return 0

    n = 0
    for f in fs:
        try:
            txt = io.open(f, encoding="utf-8", errors="replace").read()
        except Exception as e:
            print("[ev] ⚠读不了 %s：%s ⇒ 该文件未判" % (f, e))
            continue
        for i, line in enumerate(txt.split("\n"), 1):
            for rid in REF.findall(line):
                if rid not in led:
                    print("[ev] 甲 假引用 %s:%d 引了台账里没有的 %s" % (f, i, rid))
                    n += 1
                else:
                    lack = [k for k in ("测于", "取法", "排除面") if not led[rid].get(k)]
                    if lack:
                        print("[ev] 乙 空心引用 %s:%d 的 %s 缺键 %s" % (f, i, rid, "/".join(lack)))
                        n += 1
            if REF.search(line):
                continue
            if re.search(rx_zero, line, re.M) and not any(w in line for w in okwords):
                print("[ev] 丙 裸数 %s:%d 零计数断言未带取法标记也未引 ev 号：%s" % (f, i, line.strip()[:70]))
                n += 1
    print("[ev] 共查 %d 份文书｜问题 %d 条（退码%s）" % (len(fs), n, "1" if (a.strict and n) else "0"))
    return 1 if (a.strict and n) else 0


if __name__ == "__main__":
    sys.exit(main())
