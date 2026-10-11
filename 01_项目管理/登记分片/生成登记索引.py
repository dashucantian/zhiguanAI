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

# F. 悬案清单（D-1010-W3COORD-0b5dfd98 §四；坑 022 的机器载体）
# 病根：写下「候法师另示」＝自认已尽告知，此后无人再提即烂在那里（§25 悬了 24 小时、三轮收口未重列）。
# 解法：把"我记得"换成"枚举不得不漏"——扫出全部悬案标记，按挂了几天倒序排，最老的排第一。
# ⚠只报不判结案；且**零命中＝形状失效，绝不当作"已清零"**（教训 7.1／坑 017／坑 022 同一解药）。
PENDING = re.compile(r"(候法师另示|候法师一句|候您一句|候法师裁|候裁定|候裁|候一句|候示)")
# ⚠2026-10-11 实测出本词表的**盲区**：写「候法师给开工号」「候法师发开工号」「候法师明示」「候法师一个字」
#   的行**一处都抓不到**（本轮实证：正本 :1797 批B开工号那条，法师早已裁，我把它写进销账白名单才发现它从来不是命中）。
#   本窗**不当场扩词表**——扩了会把 510 变 792（实测 +269），其中混进大量"已裁定原文"的叙述行，
#   等于中途换量具、所有已报给法师的数都得重基线。改为**把盲区量化报出**，让它每轮都可见：
PENDING_WIDE = re.compile(r"(候法师|候您|候裁|候示|候一句|候批|候另示)")
PEND_TARGETS = [os.path.join(ROOT, "01_项目管理",
                             "20261008_W3_全项目协同整合基础与首批施工契约_v0.1.md")]
PEND_TARGETS += [os.path.join(HERE, f) for f in sorted(os.listdir(HERE))
                 if f.endswith(".md") and (f.startswith("KZ-") or f.startswith("D-"))]
# ⚠2026-10-10 本窗自曝一处设计漏洞：首版只扫登记分片，而"方案稿／提请函"这一类**恰恰最会带候裁**，
#   却整类不在面内——本窗拿自己刚出的两份方案稿试跑时才抓到（两份都 0 命中）。故补两处目录顶层 md。
for _d, _pat in [("01_项目管理", lambda f: f.endswith(".md")),
                 (os.path.join("01_项目管理", "信箱", "engine"),
                  lambda f: f.endswith(".md") or f.endswith(".txt"))]:
    _p = os.path.join(ROOT, _d)
    if os.path.isdir(_p):
        PEND_TARGETS += [os.path.join(_p, f) for f in sorted(os.listdir(_p))
                         if _pat(f) and not f.startswith("00_")]
# ⚠2026-10-11 抓到一处**自己上一轮扩面时引入的**重复计数：协调正本既被显式列在 PEND_TARGETS 首位，
#   又被"01_项目管理 顶层 md"扫到一次 ⇒ 它每一处命中都算两遍（销账 8 条精确键却报已销 16 处，
#   数目对不上才暴露）。去重后 headline 数才是真的。教训同款：**改扫描面必查有没有把已在面内的东西又加一遍**。
PEND_TARGETS = list(dict.fromkeys(PEND_TARGETS))
import datetime as _dt
_today = _dt.date.today()
_hits, _unreadable, _freshmap = [], [], {}
_blind = 0
PENDING_TODAY = _dt.date.today()
# ⚠2026-10-11 第一份提醒表跑出来即抓到两处毛病，据此改判据（改完即停，不再调显示启发式）：
#  ①原「mtime＝日历今天」在**跨日会话**里失效——02:5x 跑时，23:4x 刚写的方案稿全落榜，
#    唯一上榜的是己档。改「最近 24 小时」（门6 的跨日纪律在机器侧的对应物）。
#  ②己档（巡检日志-*.txt）是**只增不删的过程留痕**，历史上每一句"候裁"都永驻其中 ⇒
#    它一处就顶掉全部展示位，且对法师零信息。故**提醒表**里把它排末位（section F 全量仍照扫，不藏）。
_FRESH_H = 24 * 3600

def _mtime_today(_p):
    try:
        import time as _t
        return (_t.time() - os.path.getmtime(_p)) <= _FRESH_H
    except Exception:
        return False

_LOGFILE = re.compile(r"^巡检日志")

# ---- 层C（法师 2026-10-11「前3准」第3条）：悬案销账白名单 ----
# 格式一行一条：`文件名[:行号]｜已裁|已撤｜日期｜依据`；不带行号＝整件销账。# 起行与空行忽略。
# ⚠白名单本身也会烂：写了却一处未命中 ⇒ 必是自消音（措辞变了／行号漂了），故**未命中条数照实报出**，不当零处理。
SOLD_PATH = os.path.join(HERE, "悬案已销.txt")
_sold_exact, _sold_file, _sold_bad, _sold_n = {}, {}, [], 0
if os.path.isfile(SOLD_PATH):
    for _sl in (read(SOLD_PATH) or "").splitlines():
        _sl = _sl.strip()
        if not _sl or _sl.startswith("#"):
            continue
        _f = [x.strip() for x in _sl.replace("|", "｜").split("｜")]
        if len(_f) < 3 or _f[1] not in ("已裁", "已撤"):
            _sold_bad.append(_sl[:40])
            continue
        _sold_n += 1
        if ":" in _f[0]:
            _k, _ln = _f[0].rsplit(":", 1)
            try:
                _sold_exact[(_k, int(_ln))] = _f[1]
            except ValueError:
                _sold_bad.append(_sl[:40])
                _sold_n -= 1
        else:
            _sold_file[_f[0]] = _f[1]

def _sold_state(_fn, _i):
    return _sold_exact.get((_fn, _i)) or _sold_file.get(_fn)

for _p in PEND_TARGETS:
    _txt = read(_p)
    if _txt is None:
        _unreadable.append(os.path.basename(_p))
        continue
    # ⚠2026-10-11 修一处既有缺陷：原写 `basename[:-3]` 只适配 .md，扫面扩到 .txt 后
    #   `巡检日志-*.txt` 会留一个尾点（`…0b5dfd98.`）⇒ 白名单键永远对不上。改 splitext。
    _bn = os.path.basename(_p)
    _fn = os.path.splitext(_bn)[0]
    _age_src = added.get(_bn) if added else None
    for _i, _ln in enumerate(_txt.splitlines(), 1):
        if not PENDING.search(_ln):
            if PENDING_WIDE.search(_ln):
                _blind += 1
            continue
        _s = _ln.strip().lstrip(">|# ").replace("|", "｜")
        if len(_s) > 56:
            _s = _s[:56] + "…"
        _days = ""
        if _age_src:
            try:
                _days = (_today - _dt.datetime.strptime(_age_src[:10], "%Y-%m-%d").date()).days
            except Exception:
                _days = ""
        _hits.append((_days if _days != "" else -1, _fn, _i, _s))
        if _mtime_today(_p):
            _freshmap[(_fn, _i)] = True
# 层C：分流为「现势悬案」与「已销」
_sold_hits = [h for h in _hits if _sold_state(h[1], h[2])]
if _sold_hits:
    _hits = [h for h in _hits if not _sold_state(h[1], h[2])]
_sold_used = set()
for _d, _fn, _i, _s in _sold_hits:
    _sold_used.add((_fn, _i) if (_fn, _i) in _sold_exact else _fn)
_sold_idle = _sold_n - len(_sold_used)
_sold_cnt = {"已裁": 0, "已撤": 0}
for _h in _sold_hits:
    _sold_cnt[_sold_state(_h[1], _h[2])] += 1
_hits.sort(key=lambda x: (-x[0], x[1]))
lines += ["## F. 悬案清单（「候裁／候另示／候一句」全量枚举，按挂了几天倒序）", ""]
if not os.path.isfile(SOLD_PATH):
    lines += ["- ⚠**销账白名单 `悬案已销.txt` 不存在**（尚未建）⇒ 本轮「已销＝0」是**没得销**还是**没人销**分不清，"
              "不可读作「悬案全都还活着」（层C 未生效）。", ""]
else:
    lines += ["- 销账：白名单有效 %d 条（另有无效行 %d 条%s）｜命中现势悬案 **%d 处**（已裁 %d／已撤 %d）｜"
              "**未命中 %d 条**%s"
              % (_sold_n, len(_sold_bad), ("：" + "；".join(_sold_bad[:3])) if _sold_bad else "",
                 len(_sold_hits), _sold_cnt["已裁"], _sold_cnt["已撤"], _sold_idle,
                 "（⚠白名单自消音：措辞变了或行号漂了，须逐条复核，**不得当作已清**）" if _sold_idle > 0 else ""), ""]
if not _hits:
    lines += ["- ⚠**本轮一个悬案标记都没读到**（扫了 %d 件）。**这不是「已清零」**——最可能是标记措辞变了或文件被移动，"
              "**本项不可信，请人工核查**（同坑 017 恒空转、坑 022 不自知）。" % len(PEND_TARGETS), ""]
else:
    _old = [h for h in _hits if h[0] >= 3]
    lines += ["- 扫 %d 件｜命中 **%d** 处｜**挂 ≥3 天的 %d 处**（这些是最危险的一档：没人再提就等于放弃了）"
              % (len(PEND_TARGETS), len(_hits), len(_old)),
              "- 判据来源＝文件**首次入库日**（非文中日期，同 §25.4.3 的教训）。尚未入库者无此日 ⇒ 标「未知」排末位（**不等于不危险，只是无据可算**）。",
              "- **结案口径**：法师给字＝结案；本窗撤案＝也须写明撤与理由。**不得静默消失**（坑 022 解法 1）。",
              "- ⚠**词表盲区（量化报出，不当零）**：另有 **%d 处**用了本词表之外的说法（如「候法师给开工号／明示／一个字」），"
              "**本表抓不到**。不扩词表的理由＝扩了 %d→%d（+%.0f%%）且混进大量已裁定原文的叙述行，"
              "等于中途换量具。**要全量须人工 grep「候法师」**。"
              % (_blind, len(_hits), len(_hits) + _blind, 100.0 * _blind / max(len(_hits), 1)), ""]
    for _d, _fn, _i, _s in _hits[:14]:
        _lab = "未知" if _d < 0 else str(_d)
        lines.append("- 挂 %s 天｜`%s`:%d｜%s" % (_lab, _fn, _i, _s))
    if len(_hits) > 14:
        lines.append("- …其余 %d 处未列（本项限 14 行以压认知负荷；全量请 grep）" % (len(_hits) - 14))
    # ⚠2026-10-10 本窗第二处自曝的设计缺陷：只按"最老"倒序 ⇒ 本轮**刚写的**悬案（未入库＝age 未知）
    #   全沉到底、在 14 行截断之外永远不可见——而恰恰是这些最该被看见。故另开一段单列。
    # ⚠2026-10-10 本窗第三处自曝：首版把"未入库"一律当 age 未知，扩面后 455 条全落此档 ⇒ F′ 等于没筛。
    #   正解不按 git 判（git 只认已入库者），改按**文件 mtime＝今天**判"本轮刚写"。
    _new = [h for h in _hits if _freshmap.get((h[1], h[2]))]
    _new.sort(key=lambda h: (h[0], h[1]), reverse=False)
    _new.sort(key=lambda h: h[1], reverse=True)   # 文件名首 8 位＝日期 ⇒ 倒序＝**今天的新件排最前**（本窗第五处修：升序时 20261008 的正本吃掉全部 10 格）
    if _new:
        lines.append("")
        lines.append("### F′ 最近 24 小时写改过的文件里的悬案（最该被看见的一档，mtime 判据；跨日会话不失效）")
        lines.append("")
        # 形状修正（本窗第五处）：575 处的堆里**任何行数上限都选不对**，根因是按"命中"铺表。
        # 正解＝按**件**铺表、每行带命中数，且**今天日期的件排最前**——本档要答的是"哪几份文书有活悬案"，
        # 不是"哪一条命中最靠前"。全文一律 grep，本表只作目录。
        _by = {}
        for _d, _fn, _i, _s in _new:
            _by.setdefault(_fn, []).append((_i, _s))
        _today8 = PENDING_TODAY.strftime("%Y%m%d")
        for _fn in sorted(_by, key=lambda x: (1 if _LOGFILE.match(x) else 0, 0 if x.startswith(_today8) else 1, x))[:20]:
            _its = _by[_fn]
            lines.append("- `%s`｜%d 处｜首条 :%d %s" % (_fn, len(_its), _its[0][0], _its[0][1]))
        lines.append("- （F′ 共 %d 处、%d 件；本表按件铺、**今日日头件排最前**，全文请 grep「候裁」）" % (len(_new), len(_by)))
    if _unreadable:
        lines.append("- ⚠读不到而跳过的件：%s" % "、".join(_unreadable[:6]))
lines += ["- ⚠**旁路提示非闸门**（法师 10-09 裁「不加 `收口检查.ps1` 闸门」未被覆盖）。每次收口**须逐条重列于提请清单**，否则即坑 022 复发。", ""]

io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines).replace("\n\n\n", "\n\n"))

# ---- 层A（法师 2026-10-11「前3准」第1条）：只给法师看的 ≤8 行悬案短表 ----
# 停催令禁的是"AI 催 AI"，没禁"把法师自己该看见的东西送到他面前"⇒ 受众只有法师，不催任何窗。
# ⚠由脚本直接落盘（不靠 C3 手工写）：C3 现 enabled=false，且 cron 依附客户端进程会整日隐身；
#   脚本随开工必跑（§二bis 第5序），故这张表**只要今天有任何一扇窗开过工就必然存在**。
REMIND = os.path.join(HERE, "C3-悬案提醒-%s.md" % _today.strftime("%m%d"))
_r = ["# C3 悬案提醒｜%s（自动生成，勿手改；受众＝法师一人，不催任何窗）" % _today.isoformat(), "",
      "> 源：`生成登记索引.py` section F／F′。全量 %d 处现势悬案，此表只列 8 行；其余见 `00_总索引.md`。" % len(_hits),
      "> 销账：已裁 %d／已撤 %d（白名单 `悬案已销.txt`）。**结案请回该文件加一行，不要删原文。**" % (_sold_cnt["已裁"], _sold_cnt["已撤"]),
      "> ⚠词表盲区另有 **%d 处**（写法如「候法师给开工号」）本表抓不到 ⇒ 本表**不是全量**，零行更不等于清零。" % _blind, ""]
_old8 = [h for h in _hits if h[0] >= 3][:4]
_r.append("## 一、挂最久的四条（恐已烂：没人再提≠已放弃）")
_r.append("")
if _old8:
    for _d, _fn, _i, _s in _old8:
        _r.append("- 挂 **%d 天**｜`%s`:%d｜%s" % (_d, _fn, _i, _s))
else:
    _r.append("- （无 ≥3 天者）")
_r += ["", "## 二、最近 24 小时新提的四件（正候您一句；己档留痕排末位不上表）", ""]
_byf = {}
for _d, _fn, _i, _s in _hits:
    if _freshmap.get((_fn, _i)):
        _byf.setdefault(_fn, []).append((_i, _s))
_t8 = _today.strftime("%Y%m%d")
_byf = {k: v for k, v in _byf.items() if not _LOGFILE.match(k)}
for _fn in sorted(_byf, key=lambda x: (0 if x.startswith(_t8) else 1, x))[:4]:
    _its = _byf[_fn]
    _r.append("- `%s`｜%d 处｜首条 :%d %s" % (_fn, len(_its), _its[0][0], _its[0][1]))
if not _byf:
    _r.append("- （最近 24 小时无新写改的悬案件）")
_r += ["", "---",
       "- 另有 %d 处未列（≥3 天共 %d 处／近 24h 件共 %d 件）。**本表不是全量，零行也不等于清零。**"
       % (len(_hits) - len(_old8) - sum(len(v) for v in list(_byf.values())[:4]),
          len([h for h in _hits if h[0] >= 3]), len(_byf)),
       "- ⚠已知局限（如实留档，本窗到此停手不再调显示启发式）：①己档与历史文书里的「候裁」字样"
       "**分不清是活悬案还是当时留痕**，故本表把己档整类排除；**排除不等于其中无活悬案**，"
       "全量仍见 `00_总索引.md` section F。②**累积型正本**（协调正本 2000 行）因长期被改写，"
       "在「近 24 小时」这一档里几乎永远占掉一格且首条常是表格残行——本窗判其为**次优非错**，"
       "故只记不改（再调下去就正是坑 022 里那个「不停调显示启发式」的形态）。"]
io.open(REMIND, "w", encoding="utf-8", newline="\n").write("\n".join(_r) + "\n")

print("写出", OUT, len(lines), "行；分片", len(frag), "条；KZ标题", len(kz_head), "；D", len(dh), "；日志号", len(nums))
print("悬案提醒", REMIND, len(_r), "行｜现势", len(_hits), "处｜已销", len(_sold_hits), "处｜白名单未命中", _sold_idle, "条")
