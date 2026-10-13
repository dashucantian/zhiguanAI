# -*- coding: utf-8 -*-
"""一次吐出全部计数形状＋真退出码 —— 调研第 4 条落地（只读，不改任何窗的行为）

治的病（本仓 10-13／10-14 实测踩过）：
  · 同一个词同一文件，子串 33 行／出现 42 次／-w 16 行／-E \\b 只 10 行（中文全角标点紧邻）
    ——只报一个数＝必然吵架（卡 044 形状轴）
  · `cmd | tail` 之后取 $? 取到的是 tail 的，连着两轮记下假的 exit 0（卡 047）
  · 行数用 split("\\n") 与 LF 计数在文件末尾无换行时差 1（10-13 第 25 处）
  · 拿两个不同检索面的数相减当子集（10-13 第 20 处／10-14 第 31 处）

用法：
  python 01_项目管理/语料工程/measure.py --path <文件或目录> --pattern '<正则或字面>' [--fixed]
输出：一张**必须整块粘贴**的表（含每个形状的数、面、时刻、命令原样、退码）。
"""
import argparse, datetime, io, json, os, re, subprocess, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def sh(argv):
    """跑一条命令，返回 (退码, stdout, stderr)。退码取的是**进程本身**的，不取管道尾段。"""
    p = subprocess.run(argv, capture_output=True)
    return (p.returncode,
            p.stdout.decode("utf-8", "replace"),
            p.stderr.decode("utf-8", "replace"))


def count_file(path, pat, fixed):
    raw = io.open(path, "rb").read()
    text = raw.decode("utf-8", "errors=" + '"replace"'.strip('"'))
    lf = raw.count(b"\n")
    # 行数用 LF，不用 split("\n")：末尾无换行时两者差 1
    trailing_no_newline = (raw.endswith(b"\n") is False and len(raw) > 0)
    if fixed:
        rx = re.compile(re.escape(pat))
    else:
        rx = re.compile(pat)
    lines_hit = sum(1 for l in text.split("\n") if rx.search(l))
    occurrences = len(rx.findall(text))
    # 词边界两式：Python \\b 与 grep -w 对中文标点行为不同，分开报
    wordlike = len(re.findall(r"(?<![\w一-鿿])" + rx.pattern + r"(?![\w一-鿿])", text))
    return dict(lf=lf, cr=raw.count(b"\r"), bytes=len(raw),
                trailing_no_newline=trailing_no_newline,
                lines_matched=lines_hit, occurrences=occurrences,
                word_boundary_py=wordlike)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--fixed", action="store_true", help="按字面匹配（默认按 Python 正则）")
    ap.add_argument("--exclude", default="_analysis_tmp,output",
                    help="排除面，逗号分隔；写进输出以免'取证面被取证人污染'（卡 044 丁型）")
    a = ap.parse_args()

    excl = [e.strip() for e in a.exclude.split(",") if e.strip()]
    targets = []
    if os.path.isfile(a.path):
        targets = [a.path]
    else:
        for root, dirs, files in os.walk(a.path):
            dirs[:] = [d for d in dirs if not any(x in os.path.join(root, d) for x in excl)]
            for f in files:
                if f.endswith((".md", ".py", ".txt", ".ps1", ".json", ".mjs")):
                    p = os.path.join(root, f)
                    if not any(x in p for x in excl):
                        targets.append(p)

    ts = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    rows, agg = [], dict(lines=0, occ=0, wb=0)
    for p in targets:
        try:
            r = count_file(p, a.pattern, a.fixed)
        except Exception as e:
            r = dict(error=str(e)[:80])
        rows.append((p, r))
        if "error" not in r:
            agg["lines"] += r["lines_matched"]; agg["occ"] += r["occurrences"]; agg["wb"] += r["word_boundary_py"]

    # 交叉验证：同一判据抓一个已知存在的样本，抓不到＝判据坏，不许报"没有"（§二.16①）
    rc_grep, out_grep, err_grep = sh(["grep", "-c", "-F" if a.fixed else "-E", a.pattern] + targets[:1])
    rc_pipe = subprocess.run("false | tail -n 1", shell=True, capture_output=True).returncode
    rc_pipestatus = sh(["bash", "-c", "set -o pipefail; false | tail -n 1; echo $?"])[1].strip()

    print("=== 测量块（请整块粘贴，禁止只抄其中一个数）===")
    print("时刻        ：%s" % ts)
    print("面          ：%s%s" % (a.path, "" if os.path.isfile(a.path) else "（递归）"))
    print("排除面      ：%s  ← 不声明就是'取证面被取证人污染'" % "、".join(excl))
    print("判据        ：%s  %s" % ("字面 -F" if a.fixed else "Python 正则", repr(a.pattern)))
    print("对象数      ：%d 个文件" % len(targets))
    print("---")
    print("行数（LF 计）        ＝%d" % agg["lines"])
    print("出现次数（可多于一行）＝%d" % agg["occ"])
    print("词边界（Python 式）  ＝%d   ← 与上行不等即'匹配形状'在起作用，须一并声明" % agg["wb"])
    print("---")
    for p, r in rows[:20]:
        if "error" in r:
            print("  ERR  %s  %s" % (p, r["error"]))
        elif r["lines_matched"] or r["occurrences"]:
            print("  %5d 行 / %5d 次 / LF %4d / CR %d / %s%s  %s" % (
                r["lines_matched"], r["occurrences"], r["lf"], r["cr"],
                "无尾换行⚠" if r["trailing_no_newline"] else "尾换行OK ",
                " " * (6 if r["trailing_no_newline"] else 0), p))
    if len(rows) > 20:
        print("  …其余 %d 件未列" % (len(rows) - 20))
    print("---")
    print("退码自检（卡 047）：`false | tail` 裸取 $? ＝%d（错，取到 tail 的）；"
          "pipefail 下真值＝%s ⇒ 本工具一律 subprocess.run().returncode，不碰管道"
          % (rc_pipe, rc_pipestatus))
    print("grep 交叉验证退码＝%d（同一判据换个实现复算，不等就是形状问题不是有没有问题）" % rc_grep)
    print("命令原样        ：python %s --path %s --pattern %s%s" % (
        os.path.relpath(__file__), a.path, repr(a.pattern), " --fixed" if a.fixed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
