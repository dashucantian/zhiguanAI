#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""块一「今天卡在哪」薄发射器（纯 stdlib、零出网、单出口）。

读 01_项目管理/任务登记.md 各卡「状态」＋「最近活动」两字段（含续行），
现算停滞时长、归类卡在谁；只写 data/stuck-cards.js 一个出口。
入选／时刻／归类／排序四套口径全写进 payload.caliber；
未标日期的卡单列一组，不进 48h 排名（协调位 2026-11-11 02:5x 令）。
"""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "data" / "stuck-cards.js"
SRC = ROOT / "01_项目管理" / "任务登记.md"

CARD_RE = re.compile(r"^### (TASK-\d{8}-\d{2})\s*$")
FIELD_RE = re.compile(r"^- ([^：]{1,12})：(.*)$")
TS_FULL = re.compile(r"(20\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):([0-5]\d|\d[xX])(?::([0-5]\d))?")
TS_SHORT = re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})\s+(\d{1,2}):([0-5]\d|\d[xX])(?::([0-5]\d))?")
DATE_ONLY = re.compile(r"(?<![\d-])(\d{1,2})-(\d{1,2})(?!\d)")
RANGE_END = re.compile(r"^[–—-](\d{1,2}):([0-5]\d|\d[xX])")

DONE_WORDS = ("已完成", "已验收", "已交", "已办", "已生效", "已落盘生效", "已升为")
PENDING_WORDS = ("候", "待", "未决")

CONSEQ = {
    "法师": "您不给字，此事不动",
    "设备": "设备不就，真机验不了",
    "外环": "群里无数据，外环判据空转",
    "工具通道": "通道不通，投递停",
    "在跑": "暂无卡点，仍在跑",
    "未明": "卡点未明，需先认领",
}


def redact(s):
    return s.replace("费梦玲", "执行人").replace("宗国法师", "法师")


def fuzzy_min(s):
    return int(s.replace("x", "0").replace("X", "0"))


def infer_year(month, day, now):
    dt = datetime.datetime(now.year, month, day)
    if dt > now + datetime.timedelta(days=1):
        return now.year - 1
    return now.year


def parse_cards(text):
    cards = []
    cur = None
    field = None
    for lineno, line in enumerate(text.splitlines(), 1):
        m = CARD_RE.match(line)
        if m:
            cur = {"id": m.group(1), "line": lineno, "fields": {}}
            cards.append(cur)
            field = None
            continue
        if cur is None:
            continue
        fm = FIELD_RE.match(line)
        if fm:
            field = fm.group(1)
            cur["fields"][field] = {"start": lineno, "end": lineno,
                                    "lines": [(lineno, fm.group(2))]}
            continue
        st = line.strip()
        if field and st and not st.startswith("#"):
            f = cur["fields"][field]
            f["lines"].append((lineno, st))
            f["end"] = lineno
    return cards


def field_text(card, name):
    f = card["fields"].get(name)
    if not f:
        return "", None
    return "\n".join(t for _, t in f["lines"]), f


def leader_times(field, now):
    """条目领头时刻：字段起／行起／紧接 ** 之后；区间取终点；x 作 0。"""
    out = []
    for lineno, text in field["lines"]:
        for rx, has_year in ((TS_FULL, True), (TS_SHORT, False)):
            for m in rx.finditer(text):
                pos = m.start()
                if pos != 0 and text[pos - 2:pos] != "**":
                    continue
                if has_year:
                    year, mo, dy, hh, mm, ss = m.groups()
                    year = int(year)
                else:
                    mo, dy, hh, mm, ss = m.groups()
                    year = infer_year(int(mo), int(dy), now)
                minute = fuzzy_min(mm)
                raw = m.group(0)
                rm = RANGE_END.match(text[m.end():])
                if rm:
                    hh, minute = rm.group(1), fuzzy_min(rm.group(2))
                    ss = None
                    raw += rm.group(0)
                dt = datetime.datetime(year, int(mo), int(dy), int(hh), minute,
                                       int(ss) if ss else 0)
                out.append((dt, raw, lineno))
    if not out:
        for lineno, text in field["lines"]:
            for m in DATE_ONLY.finditer(text):
                pos = m.start()
                if pos != 0 and text[pos - 2:pos] != "**":
                    continue
                mo, dy = int(m.group(1)), int(m.group(2))
                dt = datetime.datetime(infer_year(mo, dy, now), mo, dy, 0, 0)
                out.append((dt, m.group(0), lineno))
    return out


def include_rule(status):
    if "已销" in status or "已归档" in status:
        return False
    if any(w in status for w in DONE_WORDS):
        return any(w in status for w in PENDING_WORDS)
    return True


def classify(status, duty, deadline):
    if any(k in status for k in ("待验收", "候验收", "已交待验", "待验")):
        m = re.search(r"验收＝([^；／\n]+)", duty)
        if m:
            return m.group(1).strip(), "状态属待验收类，责任位「验收＝" + m.group(1).strip() + "」"
        if "法师" in duty:
            return "法师", "状态属待验收类，责任位无验收＝而含法师"
    for k in ("候法师", "待法师", "法师一字", "法师一句", "须字", "候字", "候裁"):
        if k in status:
            return "法师", "状态命中「" + k + "」"
    m = re.search(r"(W[1-4]|VR 窗|监管位|监督位|执行窗|件主窗)", status)
    if m:
        return m.group(1), "状态命中「" + m.group(1) + "」"
    for k in ("头显", "真机", "插线", "设备", "没电"):
        if k in status:
            return "设备", "状态命中「" + k + "」"
    if "外环候数据" in status:
        return "外环", "状态含「外环候数据」"
    if "builtin" in status or "断连" in status:
        return "工具通道", "状态含 builtin/断连"
    if "进行中" in status and not any(k in status for k in ("候", "待")):
        return "在跑", "状态进行中且无候/待字样"
    both = duty + "\n" + deadline
    if "法师" in both:
        return "法师", "状态未指认，责任位/时限含法师"
    m = re.search(r"(W[1-4]|VR 窗|监管位|监督位|执行窗|件主窗)", both)
    if m:
        return m.group(1), "状态未指认，责任位/时限命中「" + m.group(1) + "」"
    return "未明", "状态与责任位/时限均未给出卡点归属"


def consequence(who):
    return CONSEQ.get(who, "该窗不交，下游停等")


def card_name(req):
    t = redact(req.replace("**", "").replace("`", "")).strip()
    return t[:18] + ("…" if len(t) > 18 else "")


def stay_text(hours):
    if hours < 24:
        return "%d 小时" % round(hours)
    return "%.1f 天" % (hours / 24)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if not SRC.exists():
        print("拒发：任务登记不存在 %s" % SRC)
        return 2
    now = datetime.datetime.now()
    cards = parse_cards(SRC.read_text(encoding="utf-8", errors="replace"))
    if not cards:
        print("拒发：一张卡都解析不出（%s）" % SRC)
        return 2
    rows, undated, excluded = [], [], 0
    for c in cards:
        status, sf = field_text(c, "状态")
        if not sf or not include_rule(status):
            excluded += 1
            continue
        duty, _ = field_text(c, "责任位")
        deadline, _ = field_text(c, "时限")
        req, _ = field_text(c, "需求原句")
        who, basis = classify(status, duty, deadline)
        row = {
            "id": c["id"],
            "name": card_name(req),
            "cardLine": c["line"],
            "statusLines": [sf["start"], sf["end"]],
            "who": redact(who),
            "whoBasis": redact(basis),
            "consequence": consequence(who),
        }
        af = c["fields"].get("最近活动")
        leaders = leader_times(af, now) if af else []
        if leaders:
            dt, raw, ln = max(leaders, key=lambda x: x[0])
            hours = (now - dt).total_seconds() / 3600
            row.update({
                "actLines": [af["start"], af["end"]],
                "lastRaw": raw,
                "lastAt": dt.strftime("%Y-%m-%d %H:%M"),
                "lastAtLine": ln,
                "hours": round(hours, 1),
                "stay": stay_text(hours),
                "recompute": "停滞＝发射时刻 − 最近活动条目领头时刻最大值；人工复算：读 任务登记.md :%d–:%d，取领头时刻最大者（区间取终点、x 作 0），与当前时刻相减" % (af["start"], af["end"]),
            })
            rows.append(row)
        else:
            row.update({
                "actLines": [af["start"], af["end"]] if af else None,
                "lastRaw": None, "lastAt": None, "hours": None,
                "stay": "未标日期",
                "recompute": "最近活动字段无可解析日期，单列不进排名",
            })
            undated.append(row)
    if len(rows) + len(undated) + excluded != len(cards):
        print("拒发：入选 %d＋未标 %d＋剔除 %d ≠ 总卡 %d"
              % (len(rows), len(undated), excluded, len(cards)))
        return 2
    rows.sort(key=lambda r: (r["hours"] < 48, -r["hours"], r["cardLine"]))
    payload = {
        "checkedAtLocal": now.strftime("%Y-%m-%d %H:%M:%S"),
        "source": SRC.relative_to(ROOT).as_posix(),
        "totalCards": len(cards),
        "included": len(rows),
        "excluded": excluded,
        "undatedCount": len(undated),
        "rows": rows,
        "undated": undated,
        "caliber": {
            "include": "状态含「已销／已归档」→剔；完成类（已完成／已验收／已交／已办／已生效／已落盘生效／已升为）须另含「候／待／未决」才入选（「挂起」不算：它指另批不指本卡）；其余入选",
            "stall": "停滞＝发射时刻 − 「最近活动」字段条目领头时刻最大值。领头＝字段起／行起／紧接 ** 之后；区间取终点；模糊分 x 作 0；仅日期按 00:00；缺年份按今年（若晚于明天则去年）。正文里引用的截止时刻／历史时刻不算活动",
            "undated": "最近活动无任何可解析日期的卡单列「未标日期」组，不进 48h 排名（协调位 2026-11-11 02:5x 令：宁可单列也不混排）",
            "caveat": "天数为登记口径：补记式登记会把停滞算小（TASK-20261108-01 即现成例），只作排序提示、不作问责",
            "who": "①待验收类→责任位「验收＝X」（缺则责任位含法师→法师）②候法师/待法师/法师一字/法师一句/须字/候字/候裁→法师 ③状态含 W1–W4/VR 窗/监管位/监督位/执行窗/件主窗→该窗 ④头显/真机/插线/设备/没电→设备 ⑤外环候数据→外环 ⑥builtin/断连→工具通道 ⑦进行中且无候待→在跑 ⑧皆未中→扫责任位＋时限（法师→法师、窗关键词→该窗），仍未中→未明",
            "sort": "≥48h 排前，再按停滞时长降序（同长按卡行号升序）；未标日期组排最后",
            "consequence": "按「卡在谁」类别给固定一句（映射表见发射器源码 CONSEQ；窗类统一「该窗不交，下游停等」）",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    js = "window.STUCK_CARDS = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    OUT.write_bytes(js.encode("utf-8"))
    print("已写 %s：总卡 %d／入选 %d／剔除 %d／未标日期 %d"
          % (OUT, len(cards), len(rows), excluded, len(undated)))
    return 0


if __name__ == "__main__":
    sys.exit(main())