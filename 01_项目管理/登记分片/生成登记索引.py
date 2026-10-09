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

# E. 分片署名行核查（D-1009-W3b 新制）
# 只查"本制之后新建"的分片。判据＝git **首次入库时刻**：早于裁定时刻者＝制前旧件，
# 一律豁免（法师裁「不回填」，把已入库旧号报成缺项＝变相逼回填，违背该裁）；
# 未入库（表里没有）者＝本制后新件，要求署名。常量带年份，跨年自动无歧义。
EFFECTIVE = "2026-10-09 15:30"      # 法师「三点同意」时刻
SIG = re.compile(r"^署｜([^｜]*)｜([^｜]*)｜([^｜]*)｜([^｜]*)$", re.M)
DATELINE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

def first_added_dates():
    """一次性扫本目录各件的首次入库时间 → {文件名: 'YYYY-MM-DD HH:MM'}。git 不可用返 None。"""
    import subprocess
    try:
        raw = subprocess.run(
            ["git", "log", "--diff-filter=A", "--name-only", "--format=%ad",
             "--date=format:%Y-%m-%d %H:%M", "--", HERE],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=30).stdout
    except Exception:
        return None
    if raw is None:
        return None
    cur, m = None, {}
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if DATELINE.match(ln):
            cur = ln
        elif cur and ln.endswith(".md"):
            k = os.path.basename(ln.replace("/", os.sep))
            if k not in m or cur < m[k]:
                m[k] = cur
    return m

added = first_added_dates()
if added is None:
    lines += ["## E. 署名行核查（`署｜任务号｜窗别｜会话短号｜AI号`）", "",
              "- ？git 不可读，**本项本轮未执行**——不静默判合格，请人工核查。", ""]
else:
    req, exempt, miss = 0, 0, []
    for fn in sorted(os.listdir(HERE)):
        if not (fn.endswith(".md") and (fn.startswith("KZ-") or fn.startswith("D-"))):
            continue
        a = added.get(fn)
        if a and a < EFFECTIVE:
            exempt += 1          # 制前已入库旧件，豁免且不回填
            continue
        req += 1
        if not SIG.search(read(os.path.join(HERE, fn)) or ""):
            miss.append(fn[:-3])
    lines += ["## E. 署名行核查（`署｜任务号｜窗别｜会话短号｜AI号`）", "",
              f"- 裁定时刻＝{EFFECTIVE}｜本制后应署 **{req}** 件，缺署名行 **{len(miss)}** 件｜制前豁免 **{exempt}** 件",
              f"- 缺项清单：{('、'.join(miss)) if miss else '无'}",
              "- 本项为**旁路提示，非提交闸门**（法师 2026-10-09 裁「不加 `收口检查.ps1` 闸门」，接受会漂）；缺项者下批提交前补一行即可，历史件不回改。", ""]

io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines).replace("\n\n\n", "\n\n"))
print("写出", OUT, len(lines), "行；分片", len(frag), "条；KZ标题", len(kz_head), "；D", len(dh), "；日志号", len(nums))
