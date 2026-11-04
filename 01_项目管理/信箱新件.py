# -*- coding: utf-8 -*-
"""信箱新件：开工先跑一次，按 mtime 列近 N 小时的新件，并标出未入库者。
立据：2026-11-05 协调位自认——四封他窗来信只读到一封，原因是没有固定动作。
用法：
    python 信箱新件.py            # 默认近 24 小时
    python 信箱新件.py 6          # 近 6 小时
    python 信箱新件.py 72         # 近 3 天
"""
import io, os, subprocess, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = r"D:\Project\zhiguanAI"
ENG = os.path.join(ROOT, "01_项目管理", "信箱", "engine")
hours = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
cutoff = time.time() - hours * 3600

# 已入库件名（一次 git 调用，避免逐件 subprocess）
try:
    tracked = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "01_项目管理/信箱/engine/"],
        capture_output=True).stdout.decode("utf-8", "replace").split("\n")
    tracked = {os.path.basename(x.strip()) for x in tracked if x.strip()}
except Exception:
    tracked = set()

rows = []
for f in os.listdir(ENG):
    p = os.path.join(ENG, f)
    if not os.path.isfile(p):
        continue
    m = os.path.getmtime(p)
    if m < cutoff:
        continue
    rows.append((m, f, os.path.getsize(p)))

rows.sort(reverse=True)
print(f"信箱 engine：近 {hours:g} 小时新件 {len(rows)} 件（按 mtime 降序）")
print(f"{'时刻':<17} {'字节':>7}  入库  件名")
print("-" * 100)
unread = 0
for m, f, sz in rows:
    t = time.strftime("%m-%d %H:%M:%S", time.localtime(m))
    ok = "已入" if f in tracked else "未入"
    if f not in tracked:
        unread += 1
    print(f"{t:<17} {sz:>7}  {ok}  {f}")
print("-" * 100)
print(f"合计 {len(rows)} 件｜未入库 {unread} 件")
if unread:
    print("\n⚠ 未入库件＝只有工作树一份。按纪律本窗不代提交他窗件；")
    print("   但公约数是：**开工先跑本脚本，再动手**——别靠想起来才翻信箱。")