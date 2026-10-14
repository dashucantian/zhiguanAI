"""待裁单销号自检（只读）：改过页面之后，逐号比对改动前后，证明没有"少写一行"。

背景：这一页是法师唯一的决策收件面。10-13 曾整页复位搬走四行未点名（W3 第 26 处自咬），
10-14 又一处补丁脚本按旧形制整段替换、把 P37 抹了一次（当场恢复，见 KZ-1014 §四⑫）。
⇒ 凡本窗动过这一页，收尾必跑本脚本；丢号＝当轮事故，不许用"已决里另有此号"糊过去。

取法：改动前基准＝HEAD 版（`git show HEAD:01_项目管理/待裁单.md`）；现势＝工作树版。
号集合＝正文里出现的 `P\\d+`（含活行标题、已决行首、已销段），大小写与撇号 P13′ 一并收。
"""
import re
import subprocess
import sys

PATH = "01_项目管理/待裁单.md"


def nums(text):
    out = set()
    for m in re.finditer(r"P\d+\u2032?|\*\*P\d+\u2032?\*\*", text):
        out.add(m.group(0).replace("**", ""))
    return out


def live(text):
    return {m.group(0)[3:].split()[0] for m in re.finditer(r"^## P\d+ .*", text, flags=re.M)}


try:
    old = subprocess.run(["git", "show", "HEAD:" + PATH], capture_output=True).stdout.decode("utf-8")
    import io
    new = io.open(PATH, encoding="utf-8").read()
except Exception as exc:  # 读不到基准就别报绿（坑 039④）
    print("BAD 取数失败：%r —— 本自检不可信" % (exc,))
    sys.exit(2)

o, n = nums(old), nums(new)
lost = sorted(o - n)
added = sorted(n - o)
lo_old, lo_new = live(old), live(new)

print("基准＝HEAD 版｜现势＝工作树版（取法：脚本内 git show ＋ io.open，测时现跑）")
print("活行数 改动前 %d → 现势 %d ｜ 现势活行＝%s" % (len(lo_old), len(lo_new), "、".join(sorted(lo_new)) or "无"))
print("逐号集合 改动前 %d 个 → 现势 %d 个" % (len(o), len(n)))
if lost:
    print("BAD 丢号 %d 个：%s —— 整段替换或复位搬行走的，必须当轮复列或点名销行" % (len(lost), "、".join(lost)))
    sys.exit(1)
print("OK 无丢号｜新增号：%s" % ("、".join(sorted(added)) or "无"))
