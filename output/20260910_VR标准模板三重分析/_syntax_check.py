"""改 vr_feedback.html 后的语法校验（防上次模板串未闭合改坏实机页面的覆辙）。
提取三个 script 块，用 node --check 做 ES 语法解析；临时文件用毕即删。"""
import os, re, subprocess, sys

BASE = r"C:\Users\tiand\OneDrive\zhiguanAI"
HTML = os.path.join(BASE, "vr_feedback.html")
TMP = os.path.join(BASE, "output", "20260910_VR标准模板三重分析")
html = open(HTML, encoding="utf-8").read()

# module 块（主逻辑，含本次 CAL 编辑）→ .mjs（node 才认 import）
mm = re.search(r'<script type="module">(.*?)</script>', html, re.S)
# 两个无属性普通块（开头工具 + 末尾 HUD）
plains = re.findall(r'<script>(.*?)</script>', html, re.S)

jobs = [("module主逻辑", mm.group(1), "_chk_module.mjs")]
for i, src in enumerate(plains):
    jobs.append((f"plain块{i+1}", src, f"_chk_plain{i+1}.mjs"))  # 一律 .mjs，兼容含 import 的块

fail = 0
for label, src, fname in jobs:
    path = os.path.join(TMP, fname)
    open(path, "w", encoding="utf-8").write(src)
    r = subprocess.run(["node", "--check", path], capture_output=True, text=True)
    lines = len(src.splitlines())
    if r.returncode == 0:
        print(f"[语法OK ] {label:12s} {lines:4d} 行")
    else:
        fail += 1
        print(f"[语法FAIL] {label:12s} {lines:4d} 行")
        print(r.stderr.strip()[:600])
    os.remove(path)   # 临时文件显式删除（agent 自产物）

print("\n结论：" + ("全部脚本块语法通过，可安全交付实机" if fail == 0 else f"{fail} 个块语法错误，禁止交付"))
sys.exit(1 if fail else 0)
