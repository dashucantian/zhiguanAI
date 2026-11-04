# -*- coding: utf-8 -*-
"""回件接头检查：核「①执行位置可解析 ②件内任务号存在于任务登记」两条。
立据：20261104_中环联结件_号区账件四线打通_v1.md §五
性质：只告警、不拦截（先看误报率）；不改主闸、不改任何回件。"""
import io, os, re, sys, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = r"D:\Project\zhiguanAI"
ENG = os.path.join(ROOT, "01_项目管理", "信箱", "engine")
REG = os.path.join(ROOT, "01_项目管理", "任务登记.md")

# 1. 号集：任务登记里的全部 TASK 号
reg = open(REG, encoding="utf-8").read()
VALID = set(re.findall(r"TASK-\d{8}-\d{2}", reg))
print(f"任务登记号集：{len(VALID)} 个")

TASK_RE = re.compile(r"TASK-\d{8}-\d{2}")
# ②「执行位置」取值：同一行或该表格行
POS_RE = re.compile(r"执行位置\s*[|｜:：]\s*([^|\n]{2,120})")

def parse_pos(v):
    """可解析＝真实 _worktrees 路径 或 明写主树（须带理由）"""
    v = v.strip().strip("*` ")
    if "_worktrees" in v or "_worktrees" in v.replace("\\", "/"):
        p = v
        m = re.search(r"(_worktrees[\\/][^\s|）)]+)", v)
        cand = os.path.join(ROOT, m.group(1).replace("/", "\\")) if m else None
        if cand and os.path.isdir(cand):
            return True, "worktree 路径在盘"
        if cand:
            return False, f"写成 worktree 路径但盘上没有：{m.group(1)}"
        return True, "含 _worktrees（路径形态待人看）"
    if "主树" in v:
        return (True, "明写主树") if len(v) > 6 else (False, "只写『主树』未附理由")
    return False, "不可解析值（既非 _worktrees 路径也非主树＋理由）"

files = sorted(glob.glob(os.path.join(ENG, "*.md")))
# 回件 vs 派单的判别：回件有自己的「运行轨迹与恢复点」小节标题；
# 派单只是在正文里提到这套模板（首轮实测：不加这条判别，我自己的派单全被误抓）
SEC_RE = re.compile(r"^#{1,4}\s*.*运行轨迹与恢复点", re.M)
seven, skipped = [], []
for f in files:
    t = open(f, encoding="utf-8", errors="replace").read()
    if SEC_RE.search(t):
        seven.append((f, t))
    elif "运行轨迹与恢复点" in t or "中断点／未做" in t:
        skipped.append(os.path.basename(f))
print(f"扫描 {len(files)} 件｜真回件（含本段小节标题）{len(seven)} 件｜仅提及七段模板而跳过 {len(skipped)} 件\n")
if skipped:
    print("  跳过（派单/引用类，非回件）：")
    for s in skipped[:8]:
        print(f"    - {s}")
    print()

bad_pos, bad_task, ok = [], [], 0
for f, t in seven:
    name = os.path.basename(f)
    # ① 执行位置
    m = POS_RE.search(t)
    if m:
        good, why = parse_pos(m.group(1))
        if not good:
            bad_pos.append((name, m.group(1).strip()[:60], why))
    else:
        bad_pos.append((name, "（无此行）", "缺『执行位置』"))
    # ② 任务号
    ids = set(TASK_RE.findall(t))
    if not ids:
        bad_task.append((name, "（无号）", "件内无 TASK 号"))
    else:
        ghost = ids - VALID
        if ghost:
            bad_task.append((name, "、".join(sorted(ghost)), "号不在任务登记"))
        else:
            ok += 1

print("=== ①『执行位置』不可解析 ===")
if bad_pos:
    for n, v, w in bad_pos:
        print(f"  ✗ {n}\n      值: {v}\n      因: {w}")
else:
    print("  全过")
print(f"\n=== ② 任务号不在登记 ===")
if bad_task:
    for n, v, w in bad_task:
        print(f"  ✗ {n}\n      号: {v}\n      因: {w}")
else:
    print("  全过")
print(f"\n=== 汇总 ===\n  七段件 {len(seven)}｜号合规 {ok}｜位置不合 {len(bad_pos)}｜号不合 {len(bad_task)}")
print("  口径：本检查只告警不拦截；『历史轮不回改』——只对新增件生效")