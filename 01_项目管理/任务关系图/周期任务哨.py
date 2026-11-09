#!/usr/bin/env python -X utf8
# 周期任务哨（01_项目管理/任务关系图/周期任务哨.py）
#
# 缘起：法师 2026-10-12 22:4x 问「P7 由月扫改周扫——不建定时任务可以，但怎么做到『周扫』？
#       靠他自觉、自己的记忆吗？靠人工提醒吗？可行吗？我只要结果，你要给出切实可行的方案，不能马虎。」
# 答的物＝本文件。要点：**周期任务不能靠任何一方的记性，必须有一条"到点没人干就自己响"的哨。**
#
# 机制（三条，缺一即会漂）：
#   ①判据一律来自**盘上现物**（文件或快照里真实存在的日期），不来自任何台账自报；
#   ②状态只有三种：按期／迟到 N 天／**无凭据**（连一份产出都没有＝从没跑过，这最危险，单列）；
#   ③**退出码即闸门**：全部按期 exit 0；任一迟到或无凭据 exit 1；脚本自身出错 exit 2。
#     ⇒ 沉默不等于通过（判语 017 同族：无检查点的规则不等于规则）。
#
# 边界（写死）：只读本仓文件；零写盘（连台账都不写，留痕由调用方做）；零网络；不 import 第三方库；
#   不改 `收口检查.ps1`／各 pipeline；不碰数据根 `D:\Project\Zen-EEG`；不碰 `02_修道班运营\机密-学员数据\`。
# 用法：python -X utf8 01_项目管理/任务关系图/周期任务哨.py [--today YYYY-MM-DD] [--json]
#      复算命令即本行；时刻缺省取本机 `date`（跨轮必重取，见规约 §二.13）。

import argparse
import datetime as dt
import io
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# ---- 周期任务表（唯一新增面＝下面这张表；判据路径必须是盘上真实存在的产出）----
# ⚠2026-11-09 协调位治理改造（W3·e12943a8）。四条原监控项里三条的线已停或已转按需，
#    留着只产「仍迟到」噪音（本哨 11-09 09:20 轮为此连续六轮报同一批迟到）；
#    本表改成**只盯当下真在跑的排程**。
#    依据三条：①法师 2026-11-09 字「该关停的就关停……你来给出方案，并且来落实」；
#    ②周期哨 2026-11-09 09:20 轮来件把四条处置归口＝「贵窗（协调位）或法师一字」；
#    ③本窗 11-09 09:23 处置单（20261109_W3_AI034_周期哨四条处置单_v1.md）三条拟裁。
#    摘出的四条与理由留档如下（删条不删理由，便于复原）：
#      ①「李德毅研究线·周扫（7 天）」→ 注销。线已停、件主窗 d776cb39 已冷。
#        原判据glob＝04_研究调研/*李德毅线周扫*.md（文件名前8位）。
#      ②「耗散测量·每日跑尺（cron 75baac62）」→ 从监控面摘出。10-22 停线属实
#        （11-08 台账现查该 cron enabled=false／pauseReason=manual）。
#        原判据glob＝_tmp_dissipation_log.txt（末行前10位）。
#      ③「排期源表快照重拉（7 天）」→ 降为按需：带快照开工的窗现拉现用，不设周期。
#        原判据glob＝01_项目管理/任务关系图/_records_raw.json（文件mtime）。
#      ④「登记索引派生视图重跑（第 5 序生成器）」→ 降为按需。
#        ⚠**这一条的理由在同一天变了**：本窗 11-09 09:23 原拟「保留每日」；
#        本轮现读 `git status --short -- 01_项目管理/登记分片/00_总索引.md` 仍是
#        **M（未提交，属他窗在途编辑）**，而 生成登记索引.py 是整件重写
#        ⇒ 一跑即覆盖他窗在途编辑，故「每日自动刷新」在结构上不成立，
#        不是谁偷懒。改判：**开工前按需刷新，前置条件＝该件无在途编辑**。
TASKS = [
    {
        "名": "源表早晚行级校验（cron ddca9eb5·每日 09:00 与 19:00）",
        "窗": "定时任务（无人值守）",
        "周期天": 1,
        "判据glob": ["01_项目管理/任务关系图/源表早晚校验日志.txt"],
        "日期取法": "末行前10位",
    },
    {
        "名": "C3 值守台拍（cron 8e2925ab·2026-11-09 起降为每日 09:40 一趟）",
        "窗": "定时任务（无人值守）",
        "周期天": 1,
        "判据glob": ["01_项目管理/信箱/engine/巡检日志-C3-b9f1881d.txt"],
        "日期取法": "文件mtime",
    },
]

DATE8 = re.compile(r"(20\d{6})")
MEASURED = re.compile(r"测于\s*(\d{4})-(\d{2})-(\d{2})")
PULLED = re.compile(r'"pulledAt"\s*:\s*"(20\d{2}-\d{2}-\d{2})')
LASTLINE = re.compile(r"^(20\d{2})-(\d{2})-(\d{2})")


def _days_ago(d, today):
    return (today - d).days


def find_date(task, today):
    """返回 (日期或None, 凭据说明, 命中件数)。取法一律以盘上现物为准。"""
    hits = []
    for pat in task["判据glob"]:
        for p in sorted(_glob(os.path.join(ROOT, pat))):
            hits.append(p)
    if not hits:
        return None, "盘上无任何产出件（＝从没跑过，非「今天没跑」）", 0
    latest, best = None, None
    how = task["日期取法"]
    for p in hits:
        d = None
        src = ""
        if how == "文件名前8位":
            m = DATE8.search(os.path.basename(p))
            if m:
                d = _mk(m.group(1)[:4], m.group(1)[4:6], m.group(1)[6:8])
                src = "文件名 %s" % m.group(1)
        elif how == "文件mtime":
            import time
            d = dt.date.fromtimestamp(os.path.getmtime(p))
            src = ("文件 mtime %s（取法＝盘侧 mtime；⚠该件内无「本次产出的时刻」字段，"
                   "故 mtime 只证明盘侧修改时刻，不得说成「文件内记录的执行时刻」）"
                   % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p))))
        elif how == "文件内pulledAt":
            txt = _read(p)
            m = PULLED.search(txt) if txt else None
            if m:
                y, mo, dd = m.group(1), m.group(2), m.group(3)
                d = _mk(y, mo, dd)
                src = "文内 pulledAt %s" % m.group(1)
        elif how == "末行前10位":
            txt = _read(p)
            lines = [l for l in (txt or "").splitlines() if l.strip()]
            if lines:
                m = LASTLINE.match(lines[-1].strip())
                if m:
                    d = _mk(m.group(1), m.group(2), m.group(3))
                    src = "末行日期 %s-%s-%s（共 %d 行，取法＝末行前 10 字符）" % (
                        m.group(1), m.group(2), m.group(3), len(lines))
        elif how == "文内测于":
            # ⚠索引里的「测于 MM-DD HH:MM」不带年份，跨年即失真 ⇒ 本任务改走 mtime（见上）
            txt = _read(p)
            ds = [_mk(a, b, c) for a, b, c in MEASURED.findall(txt or "")]
            ds = [x for x in ds if x]
            if ds:
                d = max(ds)
                src = "文内最新一处「测于」（全文 %d 处戳）" % len(ds)
        if d and (latest is None or d > latest):
            latest, best = d, "%s｜%s" % (os.path.relpath(p, ROOT).replace("\\", "/"), src)
    return latest, best, len(hits)


def _mk(y, mo, dd):
    try:
        return dt.date(int(y), int(mo), int(dd))
    except Exception:
        return None


def _read(p):
    try:
        return io.open(p, encoding="utf-8-sig", errors="replace").read()
    except Exception:
        return ""


def _glob(path):
    import glob
    return glob.glob(path)


def main():
    ap = argparse.ArgumentParser(description="周期任务到期哨（只读；迟到即非零退出）")
    ap.add_argument("--today", help="YYYY-MM-DD，缺省取系统日期")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        today = (dt.datetime.strptime(a.today, "%Y-%m-%d").date() if a.today
                 else dt.date.today())
    except Exception as e:
        print("FATAL｜日期取法失败：%s（不静默降级，拒绝以未知今日出结论）" % e)
        return 2

    rows, late, missing = [], 0, 0
    for t in TASKS:
        try:
            d, src, n = find_date(t, today)
        except Exception as e:
            rows.append({"任务": t["名"], "状态": "取数异常", "详情": "%r" % e})
            late += 1
            continue
        if d is None:
            rows.append({"任务": t["名"], "周期天": t["周期天"], "状态": "无凭据（从没跑过）",
                         "凭据": src, "命中件": n})
            missing += 1
            continue
        gap = _days_ago(d, today)
        over = gap - t["周期天"]
        if gap < 0:  # 反证三：产出日期晚于今日＝时钟或命名有假，绝不准静默算"按期"
            st = "时刻异常（产出日期晚于今日 %d 天）" % (-gap)
            late += 1
        elif over > 0:
            st = "迟到 %d 天" % over
            late += 1
        else:
            st = "按期"
        rows.append({"任务": t["名"], "窗": t["窗"], "周期天": t["周期天"],
                     "上次执行": str(d), "距今": "%d 天" % gap, "状态": st,
                     "凭据": "%s（命中 %d 件）" % (src, n)})

    verdict = "PASS" if (late == 0 and missing == 0) else "LATE"
    if a.json:
        print(json.dumps({"today": str(today), "verdict": verdict, "rows": rows},
                         ensure_ascii=False, indent=1))
    else:
        print("周期任务哨｜今日 %s（判据全部取自盘上现物，不取自任何自报台账）" % today)
        for r in rows:
            print("  %-52s｜%s｜%s" % (r["任务"][:52], r["状态"],
                                      r.get("上次执行", "—") + ("（距今 %s）" % r["距今"] if r.get("距今") else "")))
            print("        凭据：%s" % r.get("凭据", r.get("详情", "")))
        print("═══ %s｜按期 %d／迟到 %d／无凭据 %d" % (
            verdict, len(rows) - late - missing, late, missing))
    if missing:
        return 1
    return 1 if late else 0


if __name__ == "__main__":
    sys.exit(main())
