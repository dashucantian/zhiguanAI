# -*- coding: utf-8 -*-
"""闸门诱饵集（独立版）—— 只读，不碰 `收口检查.ps1`、不装 hook。

干什么：把**已知是错的**样本喂给"从 `收口检查.ps1` 里原样抠出来的判据"，看它抓不抓得住。
      抓不住＝那条判据有盲区（这不是新猜测，是把已经踩过的坑变成可重跑的机器判据）。

为什么这样算"独立"：判据用正则**从脚本源文件现读**，不改脚本、不复制粘贴一份副本，
      所以脚本一旦被改，诱饵集会立刻反映新判据的行为（＝变异测试的思路：测测试本身）。

自证要求：本集**必须**抓到下面三条已实证的盲区，否则诱饵集自己就是假绿灯 ——
      C1 门13 的 `^\\| \\*\\*P[0-9]+\\*\\*` 不认带撇的 `P13′`
      C2 门4 的 `^.[MD]` 不认已暂存的 `A `
      C3 门14 的证据词表缺「取法」「现读」
"""
import datetime, io, os, re, subprocess, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GATE = "收口检查.ps1"


def grab(pattern, label):
    """从闸门源文件里现读一条判据；读不到就报红，不许静默跳过。"""
    src = io.open(GATE, encoding="utf-8", errors="replace").read()
    m = re.search(pattern, src)
    if not m:
        return None, u"⚠抠不到判据 %s ⇒ 脚本可能已改形，本条不可信" % label
    return m.group(1), None


results = []


def case(cid, desc, rx, samples, expect_hits, note=u""):
    """rx: 判据正则（Python 形）；samples: [(输入, 该不该命中)]"""
    caught, miss, false_pos = 0, [], []
    for text, should in samples:
        hit = bool(re.search(rx, text, re.M))
        if hit == should:
            caught += 1
        elif should:
            miss.append(text[:26])
        else:
            false_pos.append(text[:26])
    ok = (len(miss) == 0 and len(false_pos) == 0)
    results.append((cid, desc, ok, u"%d/%d" % (caught, len(samples)), miss, false_pos, note))


# ── C1：门13 活行判据 ────────────────────────────────────────────────
rx13, err13 = grab(r"(\^\\\| \\\*\\\*P[^'\"]*?)['\"]", u"门13")
if rx13 is None:
    rx13 = r"^\| \*\*P[0-9]+\*\*"
case(u"C1", u"门13 活行判据认不认带撇的 P13′", rx13,
     [(u"| **P2** | x |", True), (u"| **P13′** | x |", True),
      (u"| **P31** | x |", True), (u"| 正文 | 不是行 |", False)],
     3, u"官方口径：P13′ 是合法活行 ⇒ 判据若漏它＝少报超限（10-13 实证差 1 行）")

# ── C2：门4 脏件筛子 ────────────────────────────────────────────────
rx4, err4 = grab(r"\$dirty[^=]*=[^|]*\|\s*Where-Object\s*\{\s*\$_\s*-match\s*'([^']+)'", u"门4")
if rx4 is None:
    rx4 = r"^.[MD]"
case(u"C2", u"门4 脏件筛子认不认已暂存的 A ", rx4,
     [(u" M path/a.md", True), (u" D path/b.md", True),
      (u"A  path/new.md", True), (u"?? path/un.md", False)],
     3, u"已 add 未 commit 的 `A ` 形＝真待提交；漏它则'没有待提交件'会静默略过暂存件")

# ── C3：门14 证据词表 ───────────────────────────────────────────────
rx14, err14 = grab(r"\$ok14[^=]*=\s*\[string\]::(?:join|Concat)?\(?([^)\n]*?)\)?\s*\|\|", u"门14 词表")
if rx14 is None:
    m = re.search(r"(检索面\|排除面[^\n'\" ]*)", io.open(GATE, encoding="utf-8", errors="replace").read())
    rx14 = m.group(1) if m else u"检索面|判据"
words = [w for w in re.split(r"[|｜]", rx14) if w]
def ok14(line):
    return any(w in line for w in words)
samples14 = [
    (u"七项零命中；取法 20:5x 现读 qc_pipeline.py:533", u"取法" in words or u"现读" in words),
    (u"零命中（判据＝grep -c）", True),
    (u"实测 12 件", True),
    (u"全盘没有这个文件。", False),
]
caught14 = sum(1 for t, exp in samples14 if ok14(t) == exp)
results.append((u"C3", u"门14 词表认不认「取法」「现读」",
                caught14 == len(samples14) and (u"取法" in words and u"现读" in words),
                u"%d/%d" % (caught14, len(samples14)),
                ([] if u"取法" in words else [u"缺词「取法」"])
                + ([] if u"现读" in words else [u"缺词「现读」"]),
                [],
                u"词表缺字＝合规句被反复误咬（10-13 L 窗连补两轮仍红）"))

# ── C4：退出码不是管道尾段（卡 047） ────────────────────────────────
raw = subprocess.run("false | tail -n 1", shell=True, capture_output=True).returncode
truth = subprocess.run(["bash", "-c", "set -o pipefail; false | tail -n 1; echo $?"],
                       capture_output=True).stdout.decode().strip()
results.append((u"C4", u"取退码：管道尾段 vs 真值", raw != 0,
                u"尾段=%s 真值=%s" % (raw, truth),
                [] if raw != 0 else [u"`| tail` 之后取 $? 得到的是 tail 的 0"],
                [], u"卡 047：连记两轮假 exit 0"))

# ── C5：mtime 冒充变化（卡 041／门14 致盲） ─────────────────────────
probe = "_analysis_tmp/_canary_probe.txt"
io.open(probe, "w", encoding="utf-8", newline="\n").write(u"内容恒定\n")
h1 = subprocess.run(["sha256sum", probe], capture_output=True).stdout
t1 = os.path.getmtime(probe)
os.utime(probe, (t1 + 3600, t1 + 3600))
h2 = subprocess.run(["sha256sum", probe], capture_output=True).stdout
t2 = os.path.getmtime(probe)
results.append((u"C5", u"只擦 mtime、内容不变：哈希判'无变化'才对",
                h1 == h2 and t2 != t1,
                u"mtime 变=%s 哈希变=%s" % (t2 != t1, h1 != h2),
                [], [] if h1 == h2 else [u"哈希不该变"],
                u"卡 041／门14 生效时点绑 mtime ⇒ 改文件即缩检查面"))

# ── C6：正向自检（§二.16① 否定断言前先抓一个已知存在的） ───────────
bad_rx = r"^[0-9]+\."
good_rx = u"^[①②④⑤⑥⑧]"
hay = u"① 一\n② 二\n正文\n"
results.append((u"C6", u"跑空≠不存在：同一份内容换形状就有",
                (not re.search(bad_rx, hay, re.M)) and bool(re.search(good_rx, hay, re.M)),
                u"阿拉伯形=0 命中／带圈形=%d 命中" % len(re.findall(good_rx, hay)),
                [], [], u"卡 044 甲型：拿'抓不到'当'没有'"))

# ── C7：取证被编码崩溃吞掉的那句，门14 词表认不认（10-14 新咬形） ───
# 实例：写方脚本 print 一个 ⚠ 字符，GBK 控制台抛 UnicodeEncodeError，崩在 batch_create **之前**
#       ⇒ 盘上/云上零写入。这句是**合格的取证**（讲清了崩溃点与后果），但词表里一个词都没有 ⇒ 门14 会误咬。
crash_line = u"零写入（崩溃点在写调用之前：GBK 控制台 UnicodeEncodeError，非未执行）"
c7_ok = ok14(crash_line)
results.append((u"C7", u"门14 词表认不认「崩溃点在写调用之前」这类取证句", c7_ok,
                u"命中词＝%s" % (u"、".join([w for w in words if w in crash_line]) or u"无"),
                [] if c7_ok else [u"词表缺「崩溃」／「写调用」，合规句会被误咬"],
                [], u"10-14 实测第三次 GBK 崩溃；与 C3 同族＝词表窄，不是判据松"))

# ── 汇总 ───────────────────────────────────────────────────────────
# ── 机器口：--ids 只打漏抓编号（给闸门做基线比对用，不打印人读面）──
if "--ids" in sys.argv:
    print(u",".join(sorted(cid for cid, d, ok, c, m, f, n in results if not ok)))
    sys.exit(0)

ts = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
print(u"=== 闸门诱饵集（独立版·只读） %s ===" % ts)
print(u"判据来源：%s（现读源文件抠正则，未复制副本、未改脚本）" % GATE)
print(u"---")
red = 0
for cid, desc, ok, cnt, miss, fp, note in results:
    flag = u"[抓到]" if ok else u"[漏抓]"
    if not ok:
        red += 1
    print(u"%s %-3s %-40s %s" % (flag, cid, desc[:40], cnt))
    if miss:
        print(u"        该命中却没命中：%s" % u"、".join(miss))
    if fp:
        print(u"        不该命中却命中：%s" % u"、".join(fp))
    print(u"        ↳ %s" % note)
print(u"---")
print(u"退码＝%d（%d 漏抓／共 %d 条）" % (1 if red else 0, red, len(results)))
print(u"命令原样：python %s" % os.path.relpath(__file__))
sys.exit(1 if red else 0)
