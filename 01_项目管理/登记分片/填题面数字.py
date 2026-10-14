"""题面数字填充器（可复用）：把暂存区实测数写进提交信息里的 @@NUM@@／@@CMD@@。

用法：python 填题面数字.py <msg 文件>
形制依据＝KZ-1014 §四⑨⑩⑪ 定句 v3：题面里的件数／增行／删行一律由命令生成，不出自我手。
"""
import io
import subprocess
import sys

path = sys.argv[1]
out = subprocess.run(["git", "diff", "--cached", "--numstat"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace")
files, adds, dels, binary, per = 0, 0, 0, 0, []
for line in out.stdout.splitlines():
    parts = line.split("\t")
    if len(parts) != 3:
        continue
    files += 1
    if parts[0] == "-" or parts[1] == "-":
        binary += 1
        per.append("%s 二进制" % parts[2].split("/")[-1])
    else:
        adds += int(parts[0])
        dels += int(parts[1])
        per.append("%s +%s -%s" % (parts[2].split("/")[-1], parts[0], parts[1]))

if files == 0:
    print("BAD 暂存区为空——不许拿空扫描面当通过（坑 039④）")
    sys.exit(1)

summary = "%d 件（增 %d／删 %d）" % (files, adds, dels)
cmd = "git diff --cached --numstat 机器求和，逐行：%s" % "、".join(per)
t = io.open(path, encoding="utf-8").read()
assert "@@NUM@@" in t and "@@CMD@@" in t, "占位符缺失"
io.open(path, "w", encoding="utf-8", newline="\n").write(
    t.replace("@@NUM@@", summary).replace("@@CMD@@", cmd))
print("STAGED:", summary, "| binary:", binary)
