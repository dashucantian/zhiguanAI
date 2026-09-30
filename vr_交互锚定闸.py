# -*- coding: utf-8 -*-
"""P0-1 交互锚定验收闸（VR 线·2026-09-30 W1 造·只读断言＋自产残留自清）

验什么（09-21《EEG×VR 交互分析》P0-1 的修复是否真成立）：
  1. 无会话时如实 409（**不静默收**、不缓存补记）；
  2. 有会话时合法动作落缓冲，未知/空动作 400（白名单＝不开放任意写入面）；
  3. 会话保存时事件真的写进契约事件流，且**带时间锚**（elapsed 单调不减）；
  4. 既有事件型别不被破坏（marker / experience-self_report / qc_done 仍在）；
  5. 换会话不串账（新会话第一条 count 归 1）。

用法：python vr_交互锚定闸.py            前置：console_server 在 8777 运行
退出码：全通过 0；任一不过 1。
残留：本闸会起一次**模拟**会话并保存，随后按法师口径（模拟数据＝删除并如实报）
      自清四件套并在末行报出删了哪些——不留验证垃圾进报告页。
"""
import glob
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("ZG_BASE", "http://127.0.0.1:8777")
fails, notes = [], []


def call(method, path, body=None, timeout=25):
    """返回 (状态码, 解析后的 dict 或原始文本)。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    try:
        return r.status, json.loads(txt)
    except Exception:
        return r.status, txt


def chk(cond, ok_msg, bad_msg):
    (notes if cond else fails).append(("✅ " if cond else "✗ ") +
                                      (ok_msg if cond else bad_msg))


def main():
    print("=" * 66)
    print("P0-1 交互锚定验收闸")
    print("=" * 66)

    rep = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "muse2-repo", "muse2-master", "report")
    os.makedirs(rep, exist_ok=True)

    def stems():
        """当前盘上所有 local_ 会话的干名集合——用**前后差集**认定本闸自产件，
        绝不用"最新一份"那种猜法（他窗此刻也可能在保存，猜错就会删别人的档）。"""
        return {os.path.basename(p).replace(".session_manifest.json", "")
                for p in glob.glob(os.path.join(rep, "local_*.session_manifest.json"))}

    def clean_new(before, tag):
        new = sorted(stems() - before)
        gone = []
        for stem in new:
            for p in sorted(glob.glob(os.path.join(rep, stem + "*"))):
                try:
                    os.remove(p); gone.append(os.path.basename(p))
                except Exception as e:
                    fails.append(f"残留删除失败 {p}：{e}")
        notes.append(f"🧹 {tag}：本闸自产的模拟会话残留已删净（{len(gone)} 件）"
                     + ("：" + "、".join(gone) if gone else "（无新件）"))
        return new

    # ── 1. 无会话必须 409 ────────────────────────────────────────
    st0, b0 = call("GET", "/api/monitor/status")
    if isinstance(b0, dict) and b0.get("running"):
        fails.append("前置不满足：已有监测会话在跑，本闸不抢他人在用的会话（请先停）")
        print("\n".join(notes + fails))
        sys.exit(1)
    code, body = call("POST", "/api/vr/event", {"action": "enter", "detail": "无会话试探"})
    chk(code == 409, f"无会话 → 409 如实拒收（原因：{(body or {}).get('detail') if isinstance(body, dict) else body}）",
        f"无会话应 409，实得 {code} {body}")

    # ── 2. 起一次模拟会话，验白名单与计数 ─────────────────────────
    before1 = stems()          # 起会话前先记盘上存量，事后用差集认定自产件
    code, body = call("POST", "/api/monitor/start",
                      {"simulate": True, "adapter": None,
                       "note": "P0-1 验收闸自产·模拟数据·用后即删"})
    chk(code == 200, "模拟会话已起（验证用，非真机数据）", f"起会话失败 {code} {body}")
    if code != 200:
        print("\n".join(notes + fails)); sys.exit(1)
    time.sleep(3.2)

    seq = [("enter", "vr_feedback"), ("sound_on", "开声音"),
           ("model_load", "4.glb"), ("vr_enter", "进 VR")]
    counts = []
    for act, det in seq:
        code, body = call("POST", "/api/vr/event", {"action": act, "detail": det})
        ok = code == 200 and isinstance(body, dict) and body.get("ok")
        counts.append((body or {}).get("count") if isinstance(body, dict) else None)
        chk(ok, f"动作 {act:<11} → 200，累计第 {counts[-1]} 条，"
                f"elapsed={ (body or {}).get('elapsed_sec') }s",
            f"动作 {act} 失败 {code} {body}")
    chk(counts == [1, 2, 3, 4], f"计数连续 1→4（会话内不丢不重）",
        f"计数异常：{counts}")

    code, body = call("POST", "/api/vr/event", {"action": "随便写点东西"})
    chk(code == 400, f"未知动作 → 400 白名单拦截（{(body or {}).get('detail') if isinstance(body, dict) else body}）",
        f"未知动作应 400，实得 {code} {body}")
    code, body = call("POST", "/api/vr/event", {"action": ""})
    chk(code == 400, "空动作 → 400", f"空动作应 400，实得 {code}")

    # 打点通道仍在（证明没被新端点顶掉）
    code, body = call("POST", "/api/monitor/marker", {"label": "入"})
    chk(code == 200, "既有 marker 通道未受影响", f"marker 失败 {code} {body}")
    time.sleep(1.2)

    # ── 3. 保存并核对契约事件流 ──────────────────────────────────
    code, body = call("POST", "/api/monitor/stop", {"save": True})
    chk(code == 200, "会话已停止并保存", f"停止失败 {code} {body}")
    time.sleep(2.5)
    new1 = sorted(stems() - before1)
    if len(new1) != 1:
        fails.append(f"本闸自产会话应为 1 份，差集实得 {new1}"
                     f"（用前后差集认定，不猜「最新一份」，免误删他窗档）")
    else:
        stem = os.path.join(rep, new1[0])
        with open(stem + ".session_events.jsonl", encoding="utf-8") as f:
            events = [json.loads(x) for x in f if x.strip()]
        vr = [e for e in events if e.get("kind") == "vr_interaction"]
        chk(len(vr) == 4, f"事件流内 vr_interaction 共 {len(vr)} 条（发 4 收 4，零丢失）",
            f"应 4 条，实得 {len(vr)} 条：{vr}")
        fields_ok = all(set(("action", "elapsed_sec", "ts", "session_mode"))
                        <= set(e.get("payload") or {}) for e in vr)
        chk(fields_ok, "每条都带 action/elapsed_sec/ts/session_mode（**时间锚成立＝P0-1 的核心**）",
            "有事件缺时间锚字段")
        el = [(e.get("payload") or {}).get("elapsed_sec") for e in vr]
        chk(all(a is not None for a in el) and el == sorted(el),
            f"elapsed 单调不减 {el}（不是写盘时刻糊上去的）",
            f"elapsed 非单调或为空：{el}")
        types = {e.get("type") for e in events}
        kinds = {e.get("kind") for e in events}
        chk("marker" in types or "marker" in kinds,
            f"既有事件型别仍在（type 集合 {sorted(str(t) for t in types)}）",
            f"marker 事件消失＝破了既有契约：{sorted(types)}")
        chk("self_report" in kinds, "自评 experience 通道未受影响",
            f"self_report 缺失：{sorted(kinds)}")
        # ── 4. 自清残留（法师两次裁同口径：模拟数据验证自产＝删净并如实报）──
        clean_new(before1, "第一份（保存验证）")

    # ── 5. 换会话不串账 ──────────────────────────────────────────
    before2 = stems()
    code, body = call("POST", "/api/monitor/start", {"simulate": True, "adapter": None,
                                                     "note": "P0-1 换会话不串账验证·用后即删"})
    if code == 200:
        time.sleep(2.5)
        code, body = call("POST", "/api/vr/event", {"action": "enter"})
        n = (body or {}).get("count") if isinstance(body, dict) else None
        chk(n == 1, "新会话第一条 count 归 1（**不串上一会话的账**）",
            f"新会话首条应 1，实得 {n}")
        call("POST", "/api/monitor/stop", {"save": False})
        time.sleep(2.0)
        clean_new(before2, "第二份（save:False 仍落盘＝已知行为）")
    else:
        fails.append(f"换会话验证起不来会话：{code} {body}")

    print("\n".join(notes))
    print("-" * 66)
    if fails:
        print("\n".join(fails))
        print(f"结果：**未通过**（{len(fails)} 项）")
        sys.exit(1)
    print("结果：**P0-1 交互锚定全闸通过**")


if __name__ == "__main__":
    main()
