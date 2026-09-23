# -*- coding: utf-8 -*-
"""登记分片索引生成器（幂等，随便跑）。
汇总三段 → 00_总索引.md：
  A 新分片条目（本目录 KZ-*/D-* .md，排除本脚本与README）
  B 遗留 KZ 台账（只读扫描旧大文件中的 KZ-NNN 条目标题行）
  C 遗留决策日志（只读扫描 D 编号行）
  D 工作日志（扫描各文件标题行 NNN 号；早期无号者计数注明）
原则：本脚本只读输入、只写 00_总索引.md；输入缺哪个 section 就标注缺失，不崩。
"""
import io, os, re, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "00_总索引.md")

def read(p):
    try:
        return io.open(p, encoding="utf-8").read()
    except Exception as e:
        return None

lines = ["# 登记总索引（自动生成，勿手改）",
         "", "> 生成：`python 01_项目管理\\登记分片\\生成登记索引.py` ｜ 本文件为**派生视图非真相源**，冲突重跑即修复。",
         f"> 最近生成：{datetime.datetime.now():%Y-%m-%d %H:%M}", ""]

# A. 新分片
frag = []
for fn in sorted(os.listdir(HERE)):
    if fn.endswith(".md") and fn not in ("README.md", "00_总索引.md") and (fn.startswith("KZ-") or fn.startswith("D-")):
        title = ""
        body = read(os.path.join(HERE, fn)) or ""
        m = re.search(r"^#\s+(.+)$", body, re.M)
        if m: title = m.group(1).strip()
        frag.append(f"| {fn[:-3]} | {title or '（无标题行）'} |")
lines += ["## A. 分片条目（2026-09-24 新制，一事一文件）", "", "| 编号 | 标题 |", "|---|---|"]
lines += frag if frag else ["| （暂无） | 新条目请按 README 命名落本目录 |"]
lines.append("")

# B. 遗留 KZ
tz = read(os.path.join(ROOT, "01_项目管理", "书稿勘误与订正台账.md"))
kz_head = []
if tz:
    for m in re.finditer(r"^#+\s*(KZ-\d{3})[：: ]*(.*)$", tz, re.M):
        kz_head.append(f"| {m.group(1)} | {m.group(2).strip()[:40]} |（旧大文件）")
    cnt = len(set(re.findall(r"KZ-(\d{3})", tz)))
    kz_head.insert(0, f"| 统计 | 台账内 KZ 引用去重数＝{cnt}，最大号见正文 | |")
lines += ["## B. 遗留 KZ 台账（只读，冻结）", "", "| 编号 | 标题摘要 | 载体 |", "|---|---|---|"]
lines += kz_head if kz_head else ["| ？ | 台账文件不可读，未静默跳过：请检查路径 | — |"]
lines.append("")

# C. 遗留决策日志
fj = read(os.path.join(ROOT, "01_项目管理", "止观AI项目分工与决策日志.md"))
dh = []
if fj:
    seen = set()
    for m in re.finditer(r"^\|\s*[\d-]+\s*\|\s*\*{0,2}D(\d+)[：:]\*{0,2}(.{0,38})", fj, re.M):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            dh.append((n, m.group(2).strip()))
    dh = sorted(dh)
lines += ["## C. 遗留决策日志（只读，冻结；列最近 12 条）", "", "| 编号 | 摘要 | 载体 |", "|---|---|---|"]
if fj and dh:
    for n, t in dh[-12:]:
        lines.append(f"| D{n} | {t[:38]} |（旧大文件）")
    lines.append(f"| 统计 | 共 {len(dh)} 条 D 编号行 |")
else:
    lines.append("| ？ | 决策日志不可读或无 D 行命中，未静默跳过：请人工核查 | — |")
lines.append("")

# D. 工作日志（文件本身即分片；编号双通道：新日志标题带 NNN，旧日志无号只在 README 有行）
wl = os.path.join(ROOT, "01_项目管理", "工作日志")
nums, nohead = [], 0
for fn in sorted(os.listdir(wl)):
    if fn.endswith(".md") and fn.startswith("止观AI工作日志") and fn != "README.md":
        t = read(os.path.join(wl, fn)) or ""
        m = re.search(r"^#\s*止观AI\s*工作日志\s*(\d{3})", t, re.M)
        if m: nums.append(int(m.group(1)))
        else: nohead += 1
nums = sorted(set(nums))
gaps = [n for n in range(1, (max(nums)+1 if nums else 1)) if n not in nums]
lines += ["## D. 工作日志（文件天然分片）", "",
          f"- 标题带编号的实体：{len(nums)} 个（001 起补号制后新增者自带），末号 {max(nums) if nums else '—'}",
          f"- 早期无号日志（编号仅存 README 行）：{nohead} 个",
          f"- 标题号缺号：{('、'.join(f'{n:03d}' for n in gaps)) if gaps else '无（缺号者多为无号旧档，属预期）'}",
          "- 标题级总索引仍以 `工作日志\\README.md` §七 为冻结载体；今后新日志不再手写该表，由本生成器汇总（后续版本接入）。", ""]

io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines).replace("\n\n\n", "\n\n"))
print("写出", OUT, len(lines), "行；分片", len(frag), "条；KZ标题", len(kz_head), "；D", len(dh), "；日志号", len(nums))
