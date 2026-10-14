"""提交题面复算器（机器取数，不手数）

用途：把每条提交信息标题里自报的「N 件（增 X／删 Y）」与 git 实测逐条对照，
输出不符清单。定句只保证"提哪几件"，本脚本保证"题面那几个数"。
用法：python 提交题面复算.py [起算日期 YYYY-MM-DD]
"""
import re
import subprocess
import sys
import unicodedata


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout


def norm(s):
    """全角转半角、去空白，让「增 105／删 5」与「增105删10」同一把尺。"""
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"\s+", "", s)


NUM_RE = re.compile(r"(\d+)\s*件")
ADD_RE = re.compile(r"增(\d+)")
DEL_RE = re.compile(r"删(\d+)")

# 用法：python 提交题面复算.py [起算日期 YYYY-MM-DD]  或  python 提交题面复算.py --hours 36
# 末行固定打印一条机器可读汇总 AUDIT|since=..|n=..|ok=..|mismatch=..|noclaim=..|ids=..，
# 供收口检查第 15 门直接取数——10-14 17:4x 实测 PowerShell 传 `--since=` 会静默少枚举（同一条命令 python 侧 45 笔、PS 侧 1 笔），
# 所以"枚举与比对"只放在这里做，闸门侧只读这一行（他者检验＝任何窗都能直接跑本脚本复看）。
hours = None
since = None
_argv = sys.argv[1:]
if _argv and _argv[0] == "--hours":
    hours = int(_argv[1])
elif _argv:
    since = _argv[0]
else:
    since = "2026-10-13"
# ⚠裸日期坑（本窗 10-14 实测）：`git log --since=2026-10-14` 在本机返 0 笔，补上时刻才返实数；
# 裸日期一律补 00:00:00，枚举为 0 即退码 1、不报通过（坑 039④）。
if since and re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
    since = since + " 00:00:00"
if hours is not None:
    import datetime
    since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
log = run(["git", "log", "--since=" + since, "--format=%H\x1f%ad\x1f%s\x1f%P", "--date=format:%Y-%m-%d %H:%M"])
rows = []
if not log.strip():
    print("BAD 起算 %s 枚举到 0 笔——本复算不可信：要么该时段确无提交，要么取法又被 git 吞了一层。"
          "先用 git log --oneline | head 换个取法复核，再跑本脚本。" % since)
    sys.exit(1)
for line in log.splitlines():
    if not line.strip():
        continue
    h, ad, subj, parents = line.split("\x1f")
    if len(parents.split()) > 1:  # merge commit，git show 不列改动，跳过并点名
        rows.append((h[:7], ad, subj, "MERGE-SKIP", None))
        continue
    # 解析锚点（10-14 12:3x 自纠）：原先取"第一个「件」字前 6 个字符"起截，会把标题正文里的
    # 「在途 0 件」「21 件已点」这类话当成自报数 ⇒ 造假 MISMATCH。改成尾段锚定：
    # 优先看最后一段「——」之后的部分，段内取最后一个"N 件"，增删数只在该 N 件之后找。
    tail = subj.rsplit("——", 1)[-1] if "——" in subj else subj
    tn = norm(tail)
    cand = list(re.finditer(r"(\d+)件", tn)) or list(re.finditer(r"(\d+)件", norm(subj)))
    mnum = cand[-1] if cand else None
    rest = (tn if cand and re.search(r"\d+件", tn) else norm(subj))
    rest = rest[mnum.end():] if mnum else ""
    madd = ADD_RE.search(rest)
    mdel = DEL_RE.search(rest)
    if not (mnum and madd):
        rows.append((h[:7], ad, subj, "NO-CLAIM", None))
        continue
    claimed = (int(mnum.group(1)), int(madd.group(1)), int(mdel.group(1)) if mdel else None)
    ns = run(["git", "show", "--numstat", "--format=", h])
    files, adds, dels, binary = 0, 0, 0, 0
    for l in ns.splitlines():
        parts = l.split("\t")
        if len(parts) != 3:
            continue
        files += 1
        if parts[0] == "-" or parts[1] == "-":
            binary += 1
        else:
            adds += int(parts[0])
            dels += int(parts[1])
    actual = (files, adds, dels)
    ok = (claimed[0] == actual[0] and claimed[1] == actual[1]
          and (claimed[2] is None or claimed[2] == actual[2]))
    tag = "OK" if ok else "MISMATCH"
    rows.append((h[:7], ad, subj, tag, (claimed, actual, binary)))

print("起算 %s｜共 %d 笔（机器枚举 git log --since，非手数）" % (since, len(rows)))
cnt = {}
for r in rows:
    cnt[r[3]] = cnt.get(r[3], 0) + 1
print("分类计数：", cnt)
print()
for h, ad, subj, tag, data in rows:
    if tag == "OK":
        continue
    print("%s %s %-11s %s" % (tag, h, ad, subj[:76]))
    if data:
        print("        自报=%s 实测=%s 二进制件=%d" % data)

_ids = ",".join(r[0] for r in rows if r[3] == "MISMATCH")
print("AUDIT|since=%s|n=%d|ok=%d|mismatch=%d|noclaim=%d|ids=%s"
      % (since, len(rows), cnt.get("OK", 0), cnt.get("MISMATCH", 0),
         cnt.get("NO-CLAIM", 0), _ids or "-"))
sys.exit(1 if cnt.get("MISMATCH", 0) else 0)
