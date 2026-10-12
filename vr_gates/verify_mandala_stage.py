# -*- coding: utf-8 -*-
"""件3 五段路径骨架验收闸（2026-10-10 W1·VR场景设计专责窗）

判据（规约 §五.8：每条都要有能 FAIL 的反证，否则等于没把关）：
  1. 默认关闭未破——不带 ?stage=1 时骨架不建 DOM、不自述启用（保 S1/S2 回归锚）
  2. 五段时序正确——进入≈3.0s、依次 enter→dwell→change→gather、合成四值按驻留间隔落账
  3. 红线5：退出即时生效——收束中途发退出，我方路径 ≤500ms，且退出瞬间三路确未回基线
  4. 三值分层未合并——measure/suggest/output 三列分列，未接线者为 null 不以 0 填充
  5. 红线2：退出屏上只有 采集/保存/异常，不出现绩效评分
  6. 骨架自身无 JS 错误、无 stage_error 事件
  7. 进入段跑完后场景不得仍被遮（黑场与渐隐层都必须自己撤干净）
  8. 段时钟以会话为零点（真机 16:1x「没有中间过场」回报所立；2026-10-12 补进本清单）
  9. 默认档零介入（不带 ?tension= 与无 tension 节的变体各断一层，防「启动了但值为 0」式假通过）
 10. 段3 张力成立＝有动量（会过冲）＋有回复力（回中）＋画面真被驱动（正负两向互为共模抵消对照，不取页面自述）

反证（--counter）：把页面源码改坏十一处，逐条要求对应判据 FAIL。

用法：
    python verify_mandala_stage.py            # 正跑（须 console_server 在 8777）
    python verify_mandala_stage.py --counter  # 反证跑（自起静态服务，不需 8777）
    python verify_mandala_stage.py --both
退出码：0 全过 / 1 有失败。产物：output/20261010_W1件3闸/ 下截图与 JSON。
"""
import argparse
import asyncio
import base64
import json
import os
import re
import shutil
import subprocess
import socket
import sys
import time
import urllib.request

import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "output", "20261010_W1件3闸")
COUNTER_DIR = os.path.join(ROOT, "output", "20261010_W1件3_反证")
PAGE = os.path.join(ROOT, "vr_mandala.html")

EDGE = next((p for p in [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
    if os.path.exists(p)), None)

# 调试端口与静态服务端口一律现取（free_port），不写死——写死过 9355／8806，
# 上一轮残留进程占着端口时，下一轮会连到陈旧 target 上静默挂起（10-12 实测）。
FAILS = []
SKIPS = []


def check(cond, ok_msg, fail_msg):
    if cond:
        print(f"  [PASS] {ok_msg}", flush=True)
    else:
        print(f"  [FAIL] {fail_msg}", flush=True)
        FAILS.append(fail_msg)


def expect_fail(name, ok_msg, fail_msg, fired):
    """反证专用：判据真的 FAIL 才算这条闸有牙。"""
    if fired:
        print(f"  [反证成立] {name} → {ok_msg}", flush=True)
    else:
        print(f"  [反证失败] {name} → 改坏后仍 PASS＝该判据在空转", flush=True)
        FAILS.append(f"反证失败：{name}")


async def ev(ws, expr):
    r = await send(ws, "Runtime.evaluate",
                   {"expression": expr, "returnByValue": True, "awaitPromise": True})
    return r.get("result", {}).get("value")


_m = [0]


async def send(ws, method, params=None):
    _m[0] += 1
    await ws.send(json.dumps({"id": _m[0], "method": method, "params": params or {}}))
    while True:
        m = json.loads(await ws.recv())
        if m.get("id") == _m[0]:
            if "error" in m:
                raise RuntimeError(f"{method}: {m['error']}")
            return m["result"]


async def until(base, secs):
    """按"自导航起算的绝对时刻"睡眠，避免各段误差累积。"""
    d = base + secs - time.perf_counter()
    if d > 0:
        await asyncio.sleep(d)


async def collect(ws, url, do_exit=True, gather_wait=3.0):
    """跑一遍页面，返回 {diag, events, report, panel, err, exit_call_ms, overlay}。"""
    await send(ws, "Page.navigate", {"url": url})
    base = time.perf_counter()
    await asyncio.sleep(1.2)
    err = await ev(ws, "window.__vrErr || ''")
    diag = await ev(ws, "JSON.stringify(window.__mandalaDiag ? __mandalaDiag.pathStage : null)")
    dom = await ev(ws, "JSON.stringify({badge:!!document.getElementById('stageBadge'),"
                       "exit:!!document.getElementById('btnExit'),"
                       "report:!!document.getElementById('stageReport')})")
    out = {"diag": json.loads(diag) if diag else None,
           "dom": json.loads(dom) if dom else {}, "err": err,
           "events": [], "report": None, "panel": "", "exit_call_ms": None,
           "overlay": None, "visibility": None, "pre_session": None}
    if not do_exit:
        return out
    # ⭐判据 8 的取证点：会话未起之前段机不得推进。这条是 16:1x 真机回报逼出来的
    # ——原实现段时钟以"页面加载"为零点，用户点「进入 VR」前进入段就跑完了，
    # 头显里因此"直接呈现 3D 场景、没有中间过场"。
    await until(base, 1.6)
    out["pre_session"] = json.loads(await ev(ws,
        "JSON.stringify({idx:__stageCtl.state().idx,"
        "ev:__stageCtl.events().length,"
        "wallT0:__stageCtl.state().wallT0})") or "{}")
    # 起一次（模拟）会话＝段时钟此刻归零。不点这一步，退出路径走的是"无会话"分支，
    # ourPathMs 定义上恒为 0，判据 3 就成了空转（03:4x 反证实测抓到）。
    await ev(ws, "document.getElementById('btnVR').click()")
    arm = time.perf_counter()
    # 进入段（3s）跑完后再探遮挡：黑场与进入段渐隐都不得还盖着场景。渐隐现在
    # 也在会话起点重放，所以这一探必须排在 arm 之后，否则量到的是动画进行中。
    await until(arm, 3.6)
    out["visibility"] = await ev(ws, "document.visibilityState")
    ov = await ev(ws, "JSON.stringify({load:getComputedStyle(document.getElementById('load')).display,"
                      "fade:(()=>{const f=document.getElementById('stageFade');"
                      "if(!f)return null;const c=getComputedStyle(f);"
                      "return {display:c.display,opacity:+parseFloat(c.opacity).toFixed(3)};})()})")
    out["overlay"] = json.loads(ov) if ov else None
    # 时间线（segsec=2，**自会话起点算**）：enter 0–3 → dwell 3–5 → change 5–13 → gather 13–19。
    # 落在收束早段发退出，才测得到"打断渐变"。
    await until(arm, 3.0 + 2.0 + 2.0 * 4 + gather_wait - 1.5)
    t0 = time.perf_counter()
    await ev(ws, "__stageCtl.exit()")
    # 外部计时：CDP 的 evaluate 在主线程排队，页面里若有自旋等待会被这条量到；
    # 页面自己报的 ourPathMs 属"自证"，只作对照，不当判据。
    out["exit_call_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    await asyncio.sleep(1.0)
    out["events"] = json.loads(await ev(ws, "JSON.stringify(__stageCtl.events())") or "[]")
    out["report"] = json.loads(await ev(ws, "JSON.stringify(window.__stageReport)") or "null")
    out["panel"] = await ev(ws, "(document.getElementById('stageReport')||{}).innerText || ''")
    out["err2"] = await ev(ws, "window.__vrErr || ''")
    png = await send(ws, "Page.captureScreenshot", {"format": "png"})
    with open(os.path.join(OUT, "exit_panel.png"), "wb") as f:
        f.write(base64.b64decode(png["data"]))
    return out


def judge_default_off(o):
    """判据 1：默认关闭未破。"""
    print("\n── 判据 1：默认关闭（不带 ?stage=1 不得启用骨架）──────────")
    check(o["dom"].get("badge") is False and o["dom"].get("exit") is False
          and o["dom"].get("report") is False,
          "默认态无骨架 DOM（无标识条/无退出键/无面板）",
          f"默认态出现骨架 DOM：{o['dom']}——红线：已认可版本默认呈现被改")
    check(bool(o["diag"]) and o["diag"].get("enabled") is False,
          "钩子自述 pathStage.enabled=false",
          f"钩子自述异常：{o['diag']}")


def judge_sequence(o):
    """判据 2：五段时序。"""
    print("\n── 判据 2：五段时序（enter→dwell→change→gather）────────────")
    pbe = [e for e in o["events"] if e.get("kind") == "phase_begin"]
    ph = [e["phase"] for e in pbe]
    check(ph == ["enter", "dwell", "change", "gather"],
          f"段序正确 {ph}", f"段序不符：期望 [enter,dwell,change,gather]，实得 {ph}")
    if len(pbe) >= 2:
        enter_dur = pbe[1]["atSec"] - pbe[0]["atSec"]
        check(2.6 <= enter_dur <= 3.4,
              f"进入段实测 {enter_dur:.3f}s ≈ 规格 3.0s",
              f"进入段实测 {enter_dur:.3f}s 偏离规格 3.0s")
    syn = [e for e in o["events"] if e.get("kind") == "synth"]
    check(len(syn) == 4, f"合成序列落账 4 条（measure={[e['measure'] for e in syn]}）",
          f"合成事件数 {len(syn)}≠4")
    if len(syn) == 4:
        gaps = [round(syn[i + 1]["atSec"] - syn[i]["atSec"], 3) for i in range(3)]
        check(all(1.6 <= g <= 2.4 for g in gaps),
              f"驻留间隔实测 {gaps}s（segsec=2）",
              f"驻留间隔异常 {gaps}——合成契约 §三 的时长没在把关")


def judge_exit_immediate(o):
    """判据 3：红线5 退出不等待渐变。主判据＝外部实测退出调用返回耗时。"""
    print("\n── 判据 3：红线5（收束中途退出须即时生效，不等 6s 渐变）────")
    rep = o["report"]
    if not rep:
        check(False, "", "退出报告未生成——退出路径没跑通")
        return
    ext = o.get("exit_call_ms")
    check(ext is not None and ext <= 500,
          f"外部实测：退出调用 {ext}ms 返回 ≤500ms（不等渐变）",
          f"外部实测：退出调用 {ext}ms 超 500ms——退出在等待某件事")
    c = rep["conditions"]["xrSessionEnded"]
    check(c.get("verdict") == "PASS" and c.get("endToEndMs") is not None,
          f"会话结束事件已收到（我方报 ourPathMs={c.get('ourPathMs')}、"
          f"端到端 {c.get('endToEndMs')}ms）",
          f"会话结束未成立：{c}")
    b = rep["conditions"]["feedbackAtBaseline"]
    check(b.get("phaseAtExit") == "gather"
          and b.get("phaseElapsedSecAtExit") is not None
          and b["phaseElapsedSecAtExit"] < b.get("gatherSecPlanned", 6),
          f"退出发生在收束第 {b.get('phaseElapsedSecAtExit')}s（计划 {b.get('gatherSecPlanned')}s）"
          "＝渐变确被打断",
          f"退出时不在收束段早段（phase={b.get('phaseAtExit')},"
          f"elapsed={b.get('phaseElapsedSecAtExit')}）——本判据可能空跑")
    check(b.get("maxRelDeltaAtExitInstant") is not None
          and b["maxRelDeltaAtExitInstant"] > 0,
          f"退出瞬间三路偏离基线 {b.get('maxRelDeltaAtExitInstant')}（锁定后归 0，"
          "两个数都记＝不自证）",
          "退出瞬间偏离量为 0——收束已跑完，本例没测到「退出打断渐变」")


def judge_three_values(o):
    """判据 4：三值分层未合并。"""
    print("\n── 判据 4：三值分层 measure/suggest/output 不得合并 ────────")
    syn = [e for e in o["events"] if e.get("kind") == "synth"]
    if not syn:
        check(False, "", "无合成事件可判")
        return
    ok = all(("measure" in e and "suggest" in e and "output" in e) for e in syn)
    check(ok, "三键齐备（缺项留位不以 0 填充）", "三值分层缺键")
    merged = [e for e in syn if e["suggest"] == e["measure"] or e["output"] == e["measure"]]
    check(not merged, "suggest/output 未被写成 measure 的副本",
          f"三值被合并：{[(e['seqIndex'], e['measure'], e['suggest'], e['output']) for e in merged]}")
    zero_fill = [e for e in syn if e["suggest"] == 0 or e["output"] == 0]
    check(not zero_fill, "未接线者留 null（不以 0 冒充 0.0 测量值）",
          f"发现 0 填充：{[e['seqIndex'] for e in zero_fill]}")


def judge_no_score(o):
    """判据 5：退出屏上只有三态、无绩效评分。"""
    print("\n── 判据 5：红线2（退出后只显示 采集/保存/异常，不弹评分）───")
    panel = o["panel"] or ""
    hit = re.findall(r"得分|评分|绩效|score|成绩", panel, re.I)
    check(not hit, "屏上无绩效评分字样", f"屏上出现评分字样：{sorted(set(hit))}")
    need = ["是否采集", "是否保存", "异常"]
    check(all(k in panel for k in need), f"屏上三态齐备 {need}",
          f"屏上缺项：{[k for k in need if k not in panel]}")


def judge_overlay(o):
    """判据 7：进入段跑完后，场景不得仍被任何全屏层盖住。"""
    print("\n── 判据 7：进入段后场景不得被遮（真机「打开只剩空白」回报所立）──")
    ov = o.get("overlay")
    if not ov:
        check(False, "", "遮挡探针未取到——本判据没跑成，不等于通过")
        return
    check(ov.get("load") == "none", "黑场 #load 已撤",
          f"#load 仍在显示：{ov.get('load')}——骨架把主视图夺走了")
    f = ov.get("fade")
    clear = f is None or f.get("display") == "none" or f.get("opacity", 0) < 0.02
    check(clear, f"进入段渐隐已尽（页面 {o.get('visibility')}／fade＝{f}）",
          f"进入段结束后仍有全屏遮挡：{f}")


def judge_clock_anchor(o):
    """判据 8：段时钟零点＝会话起点（不是页面加载）。"""
    print("\n── 判据 8：段时钟以会话为零点（真机 16:1x「没有中间过场」所立）──")
    pre = o.get("pre_session")
    if pre is None:
        check(False, "", "会话前探针未取到——本判据没跑成，不等于通过")
        return
    check(pre.get("idx") == 0 and pre.get("ev") == 0,
          f"会话未起时段机零推进（idx={pre.get('idx')}／事件 {pre.get('ev')} 条）",
          f"页面加载即起段：会话前 idx={pre.get('idx')}、事件 {pre.get('ev')} 条 ⇒ "
          "进入段在用户点「进入 VR」之前就跑完，头显里必然「没有中间过场」")
    sb = [e for e in o["events"] if e.get("kind") == "session_begin"]
    check(bool(sb) and sb[0]["atSec"] <= 0.05,
          f"session_begin 落在零点（atSec＝{(sb[0]['atSec'] if sb else None)}）",
          f"session_begin atSec＝{(sb[0]['atSec'] if sb else '缺失')}＞0.05 ⇒ 时钟起点不是会话")
    pbe = [e for e in o["events"] if e.get("kind") == "phase_begin"]
    check(bool(pbe) and pbe[0]["phase"] == "enter" and pbe[0]["atSec"] <= 0.3,
          f"进入段自会话起点开跑（atSec＝{(pbe[0]['atSec'] if pbe else None)}）",
          f"进入段首事件不在会话起点：{(pbe[0]['atSec'] if pbe else '无')}")


def judge_no_error(o):
    print("\n── 判据 6：骨架自身无错 ──────────────────────────────────")
    check(not (o.get("err2") or o.get("err")),
          "全程 __vrErr 为空", f"JS 错误：{(o.get('err') or o.get('err2'))[:120]}")
    bad = [e for e in o["events"] if e.get("kind") == "stage_error"]
    check(not bad, "无 stage_error 事件", f"骨架自报错：{bad[:1]}")


# ── 反证：把页面改坏，逐条要求对应判据 FAIL ────────────────────────
TENSION_MUTANTS = {"默认档也挂偏移", "无回复力只剩阻尼", "临界阻尼不过冲", "段长非整数个摆"}

EPS_T = 0.005   # 段末回中容差：实测 0.0007@60fps／0.0013@30fps，而非整数摆回数的残值约 0.0067

async def collect_tension(ws, url, sample_from=4.6, sample_secs=8.8, tick=0.4):
    """跑一遍带张力层的页，采段3 全周期的**实时场景读数**。
    采样窗口按 segsec=2 的时线排：enter 0-3 → dwell 3-5 → change 5-13 → gather 13-19，
    故 4.6 起、采 8.8 秒，覆盖整个变化段并越过段末一点，才拿得到"回中"那一探。"""
    await send(ws, "Page.navigate", {"url": url})
    await asyncio.sleep(1.2)
    cfg = json.loads(await ev(ws, "JSON.stringify(window.__mandalaDiag && __mandalaDiag.pathStage"
                                  " ? (typeof __mandalaDiag.pathStage.tension === 'undefined'"
                                  " ? null : __mandalaDiag.pathStage.tension) : null)") or "null")
    await ev(ws, "document.getElementById('btnVR').click()")
    arm = time.perf_counter()
    samples = []
    await until(arm, sample_from)
    stop = arm + sample_from + sample_secs
    while time.perf_counter() < stop:
        v = await ev(ws, "JSON.stringify(window.__mandalaDiag.pathStage.tensors)")
        # 未介入时这里是字符串 "null"（JSON.stringify(null）），不是 Python 假值——
        # 判据 9 要的正是"零样本"，所以这条必须显式认掉，否则崩在解析上。
        d = json.loads(v) if v and v != "null" else None
        if d:
            samples.append({"at": round(time.perf_counter() - arm, 3),
                            "t": d.get("output"), "vt": d.get("vt"),
                            "flips": d.get("flips"), "live": d.get("live") or {}})
        await asyncio.sleep(tick)
    fin = json.loads(await ev(ws, "JSON.stringify(window.__mandalaDiag.pathStage.tensors)") or "null")
    evs = json.loads(await ev(ws, "JSON.stringify(__stageCtl ? __stageCtl.events() : [])") or "[]")
    return {"url": url, "cfg": cfg, "final": fin, "samples": samples,
            "begin": next((e for e in evs if e.get("kind") == "tension_begin"), None),
            "end": next((e for e in evs if e.get("kind") == "tension_end"), None)}


def judge_tension_default(off, s1):
    """判据 9：默认档零介入。三层各断一件事——只断「值为 0」会放过「启动了但没动」这种假通过。"""
    print("\n── 判据 9：默认档零介入（不带 ?tension= 与无 tension 节的变体）─────")
    cfg = off["cfg"]
    check(cfg is not None and cfg.get("enabled") is False,
          "v4 不带 ?tension：注册表有节但 enabled=false（本层根本没启动）",
          f"v4 不带 ?tension 却已启用：{cfg}——红线：默认呈现被介入，已认可版本不再是入口")
    check(off["final"] is None and not off["samples"],
          "同一页跑到段3 时刻 tensors===null、零样本（不是「启动了但值为 0」）",
          f"未挂参数却有读数：final={off['final']}，样本 {len(off['samples'])} 条")
    check(s1["cfg"] is None,
          "s1 挂 ?tension=pos：该变体注册表内无 tension 节，结构上不可能介入",
          f"s1 竞读到了 tension 节：{s1['cfg']}——单一正源被绕过，须查注册表外是否藏了第二份配置")
    check(s1["final"] is None,
          "s1 那次同样零读数（S1/S2 回归锚逐字节安全）",
          f"s1 挂上 flag 就动了：{s1['final']}")


def judge_tension_dynamics(pos, neg):
    """判据 10：张力成立＝有动量（会过冲）＋有回复力（回中）＋画面真被驱动。
    第三条用 pos/neg 两次互为对照：两者只差 ?tension 的符号，呼吸与段时钟完全共模，
    差值只可能来自张力层——所以「动了」不由页面自己声称。"""
    print("\n── 判据 10：段3 张力＝偏离与回中（正负两向共模抵消对照）───────────")
    fp, fn = pos["final"], neg["final"]
    if not fp or not fn:
        check(False, "", f"读数缺失：pos={bool(fp)} neg={bool(fn)}——本判据没跑成，不等于通过")
        return
    check(fp.get("flips", 0) >= 1 and fn.get("flips", 0) >= 1,
          f"有动量：符号翻转 正向 {fp['flips']} 次／负向 {fn['flips']} 次（至少 1 次才叫过冲）",
          f"未见翻转＝一次性推到位、没有动量：flips pos/neg = {fp.get('flips')}/{fn.get('flips')}")
    check(abs(fp["output"]) <= EPS_T and abs(fn["output"]) <= EPS_T,
          f"有回复力：段末 |t| = {abs(fp['output'])}／{abs(fn['output'])}，容差 {EPS_T}",
          f"段末没回中：pos={fp['output']} neg={fn['output']}——零点不是吸引子")
    pairs = []
    for a in pos["samples"]:
        if not neg["samples"]:
            break
        b = min(neg["samples"], key=lambda s: abs(s["at"] - a["at"]))
        vals = (a["live"].get("fog"), b["live"].get("fog"),
                a["live"].get("glow"), b["live"].get("glow"))
        if None in vals:
            continue
        pairs.append((a, b))
    if len(pairs) < 4:
        check(False, "", f"共模对照样本不足（{len(pairs)} 条）——本判据没跑成，不等于通过")
        return
    i = max(range(len(pairs)),
            key=lambda k: abs(pairs[k][0]["live"]["fog"] - pairs[k][1]["live"]["fog"]))
    j = max(range(len(pairs)),
            key=lambda k: abs(pairs[k][0]["live"]["glow"] - pairs[k][1]["live"]["glow"]))
    af, bf = pairs[i]
    ag, bg = pairs[j]
    dfog = af["live"]["fog"] - bf["live"]["fog"]
    dglow = ag["live"]["glow"] - bg["live"]["glow"]
    tf, tg = af["t"], ag["t"]
    # 阈值按 8 秒快档的实测定，不是纸面推的：雾轴要过一阶跟随 tau=34/6 约 5.67 秒，
    # 首摆 0.78 秒内只来得及走开约两成，所以共模差在快档只有 0.001 量级（默认档段长 80 秒
    # 时同一条轴的量级约为它的六倍）；光晕 tau=13/6 约 2.2 秒，跟得上，是 0.03 量级。
    check(abs(dfog) >= 0.0007 and abs(dglow) >= 0.02,
          "画面真被驱动：|dFog|max={0:.6f}（阈 0.0007）｜|dGlow|max={1:.5f}（阈 0.02）"
          .format(abs(dfog), abs(dglow)) + "——两跑只差 ?tension 符号，呼吸为共模已抵消",
          "t 在动而场景无差：dFog={0:.6f} dGlow={1:.5f}——等于自证".format(dfog, dglow))
    check((dfog < 0) == (tf > 0) and (dglow > 0) == (tg > 0),
          "极的接法对得上：t 取正时雾更薄（阳＝露）、光晕更张（明＝阳）",
          "极接反：t={0} 雾差 {1:.6f}；t={2} 光晕差 {3:.5f}——轴与两极对不上"
          .format(tf, dfog, tg, dglow))
    la, lb = pairs[-1]
    rf, rg = abs(la["live"]["fog"] - lb["live"]["fog"]), abs(la["live"]["glow"] - lb["live"]["glow"])
    check(rf <= 0.001 and rg <= 0.01,
          f"两向归于同一场景：段末 |dFog|={rf:.6f}｜dGlow|={rg:.5f}",
          f"段末两向仍差着：dFog={rf:.6f} dGlow={rg:.5f}——t 归零而场景没归零")


MUTATIONS = [
    ("默认改启用", "c1_default_on.html",
     [("const STAGE_ON = QSTAGE.get('stage') === '1';",
       "const STAGE_ON = QSTAGE.get('stage') !== '0';")], judge_default_off),
    ("进入段时长失真", "c2_enter_fast.html",
     [("const ENTER_S  = 3.0;", "const ENTER_S  = 0.2;")], judge_sequence),
    ("退出等待渐变", "c3_exit_spins.html",
     [("  const s = xrSessionRef;",
       "  { const _e = performance.now() + 1200; while (performance.now() < _e) {} }\n"
       "  const s = xrSessionRef;")], judge_exit_immediate),
    ("三值合并", "c4_merge_values.html",
     [("    suggest: null, output: null,", "    suggest: SYNTH_SEQ[i], output: SYNTH_SEQ[i],")],
     judge_three_values),
    ("屏上弹评分", "c5_score_popup.html",
     [("    '<div>异常：' + errs + '</div>' +",
       "    '<div>异常：' + errs + '</div>' + '<div>本次得分：92</div>' +")], judge_no_score),
    ("进入段遮不撤净", "c7_overlay_stuck.html",
     [("    'animation:zgEnterFade ' + ENTER_S + 's linear forwards}' +",
       "    'animation:zgEnterFade 3000s linear forwards}' +")], judge_overlay),
    ("段时钟挂在页面加载", "c8_clock_from_load.html",
     [("if (STAGE_ON && !stage.fault && xrSessionRef && !stageFreezesBreath()) stageTick(time);",
       "if (STAGE_ON && !stage.fault && !stageFreezesBreath()) stageTick(time);")],
     judge_clock_anchor),
    ("默认档也挂偏移", "c9_tension_by_default.html",
     [(": QSTAGE.get('tension') === 'neg' ? -1 : 0;",
       ": QSTAGE.get('tension') === 'neg' ? -1 : 1;")], judge_tension_default),
    ("无回复力只剩阻尼", "c10a_no_spring.html",
     [("tension.vt += (-tension.k * tension.tRaw - tension.c * tension.vt) * dt;",
       "tension.vt += (-tension.c * tension.vt) * dt;")], judge_tension_dynamics),
    ("临界阻尼不过冲", "c10b_overdamped.html",
     [("N: 2, zeta: 0.34, firstPeak: 0.85,", "N: 2, zeta: 0.99, firstPeak: 0.85,")],
     judge_tension_dynamics),
    ("段长非整数个摆", "c10c_fractional_swing.html",
     [("N: 2, zeta: 0.34, firstPeak: 0.85,", "N: 2.3, zeta: 0.34, firstPeak: 0.85,")],
     judge_tension_dynamics),
]


def build_mutants():
    os.makedirs(COUNTER_DIR, exist_ok=True)
    src = open(PAGE, encoding="utf-8").read()
    made = []
    for name, fn, repls, judge in MUTATIONS:
        s = src
        for a, b in repls:
            if a not in s:
                print(f"  [SKIP] 反证「{name}」锚文本不在页面里：{a[:40]}")
                SKIPS.append(name)
                s = None
                break
            s = s.replace(a, b, 1)
        if s is None:
            continue
        with open(os.path.join(COUNTER_DIR, fn), "w", encoding="utf-8", newline="") as f:
            f.write(s)
        made.append((name, fn, judge))
    return made


def start_static():
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
         "--directory", ROOT],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return proc, port
        except Exception:
            time.sleep(0.25)
    kill_tree(proc)
    raise RuntimeError("静态服务未起")


def free_port():
    """端口现取，不写死。写死 9355 踩过一次：上一轮 Edge 子进程没被收掉时端口仍被占，
    下一次 browser() 会连到那个**陈旧 target**上，页面是旧的、CDP 调用静默不返回，
    表现出来像"改动无效／浏览器坏了"，实际是端口串了。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def clean_profiles(keep=None):
    """_p_* 是每跑一次的临时 profile；进程已死却留着会越堆越多。删不掉就留着，不算失败。"""
    for name in os.listdir(OUT) if os.path.isdir(OUT) else []:
        if not name.startswith("_p"):
            continue
        path = os.path.join(OUT, name)
        if keep and name == os.path.basename(keep):
            continue
        try:
            shutil.rmtree(path)
        except Exception:
            pass


def kill_tree(proc):
    """Windows 下 proc.kill() 只杀启动器那一个进程，Edge 的子进程树（gpu/utility/renderer/
    crashpad）会留着继续占端口。按进程树杀；taskkill 不可用时退回 kill()。"""
    try:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except Exception:
        proc.kill()


async def browser():
    port = free_port()
    # profile 目录也一并按端口分开：Edge 对同一 user-data-dir 是单例——残留实例还在时，
    # 新启的那个会直接并入并退出，调试端口永远等不到（本轮实测踩到，报「Edge 调试端口未就绪」）。
    prof = os.path.join(OUT, "_p_%d" % port)
    proc = subprocess.Popen(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--window-size=1280,720", f"--user-data-dir={prof}",
         "--no-first-run", f"--remote-debugging-port={port}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    targets = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2) as r:
                targets = json.load(r)
            break
        except Exception:
            await asyncio.sleep(0.5)
    if not targets:
        kill_tree(proc)
        raise RuntimeError("Edge 调试端口未就绪")
    page = next(t for t in targets if t["type"] == "page")
    ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
    await send(ws, "Page.enable")
    await send(ws, "Runtime.enable")
    # 页面在无 WebXR 的环境下点「进入 VR」会走 alert()，模态框把主线程的 JS 执行连同
    # 后续所有 CDP 调用一起堵死——探针表现为"静默挂起"，极易误读成被测改动无效
    # （本窗 10-12 首轮实测栽在此）。新建文档时先把 alert 摘掉：取证面不该被一个弹窗
    # 劫持；真实告警仍由 __vrErr／事件序列覆盖，不靠这个弹窗。
    await send(ws, "Page.addScriptToEvaluateOnNewDocument",
               {"source": "window.alert=function(m){window.__lastAlert=String(m);};\n"
                          "window.confirm=function(m){window.__lastAlert=String(m);return false;};\n"
                          "window.print=function(){};"})
    return proc, ws


async def run_normal(base):
    # 显式钉 variant=s1：2026-10-10 C2 乙案后入口缺省已改指 v4lotuspond，
    # 本闸测的是骨架时序，须与入口缺省解耦（否则缺省一改，本闸读数跟着漂）。
    url_off = f"{base}/mandala?variant=s1&breath=off"
    url_on = f"{base}/mandala?variant=s1&stage=1&breath=on&segsec=2&xrmock=1"
    proc, ws = await browser()
    try:
        print("\n" + "=" * 68)
        print("正跑：默认态（不带 ?stage=1）")
        print("=" * 68)
        judge_default_off(await collect(ws, url_off, do_exit=False))
        print("\n" + "=" * 68)
        print("正跑：?stage=1 全链（segsec=2 加速，xrmock 只验退出路径时序）")
        print("=" * 68)
        o = await collect(ws, url_on, gather_wait=3.0)
        with open(os.path.join(OUT, "正跑_事件与报告.json"), "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False, indent=1)
        judge_sequence(o)
        judge_exit_immediate(o)
        judge_three_values(o)
        judge_no_score(o)
        judge_no_error(o)
        judge_overlay(o)
        judge_clock_anchor(o)
        # 判据 9／10：张力层（段3 运相）。四趟采集各约 16 秒，多耗约一分半；
        # 零介入那两趟是「默认档逐字节」这条红线的直接取证面，省不得。
        plain = f"{base}/mandala?variant=v4lotuspond&stage=1&breath=on&segsec=2&xrmock=1"
        s1on = f"{base}/mandala?variant=s1&stage=1&breath=on&segsec=2&xrmock=1&tension=pos"
        print("\n" + "=" * 68)
        print("正跑：张力层判据 9（零介入两例：v4 不带 flag／s1 挂了 flag）")
        print("=" * 68)
        o_off = await collect_tension(ws, plain)
        o_s1 = await collect_tension(ws, s1on)
        judge_tension_default(o_off, o_s1)
        print("\n" + "=" * 68)
        print("正跑：张力层判据 10（正负两向共模抵消对照）")
        print("=" * 68)
        o_pos = await collect_tension(ws, plain + "&tension=pos")
        o_neg = await collect_tension(ws, plain + "&tension=neg")
        judge_tension_dynamics(o_pos, o_neg)
        with open(os.path.join(OUT, "正跑_张力层.json"), "w", encoding="utf-8") as f:
            json.dump({"off": o_off, "s1": o_s1, "pos": o_pos, "neg": o_neg},
                      f, ensure_ascii=False, indent=1)
    finally:
        kill_tree(proc)
        clean_profiles()


async def run_counter():
    made = build_mutants()
    if not made:
        print("无可跑反证")
        return
    static, static_port = start_static()
    proc, ws = await browser()
    base = f"http://127.0.0.1:{static_port}/output/20261010_W1件3_反证"
    try:
        for name, fn, judge in made:
            print("\n" + "=" * 68)
            print(f"反证：{name}（{fn}）")
            print("=" * 68)
            before = len(FAILS)
            url = f"{base}/{fn}"
            if name == "默认改启用":
                o = await collect(ws, f"{url}?breath=off", do_exit=False)
                await _quiet(judge, o)
            elif name in TENSION_MUTANTS:
                plain = f"{url}?variant=v4lotuspond&stage=1&breath=on&segsec=2&xrmock=1"
                s1on = f"{url}?variant=s1&stage=1&breath=on&segsec=2&xrmock=1&tension=pos"
                if name == "默认档也挂偏移":
                    await _quiet(judge, await collect_tension(ws, plain),
                                 await collect_tension(ws, s1on))
                else:
                    await _quiet(judge, await collect_tension(ws, plain + "&tension=pos"),
                                 await collect_tension(ws, plain + "&tension=neg"))
            else:
                o = await collect(ws, f"{url}?stage=1&breath=on&segsec=2&xrmock=1",
                                  gather_wait=3.0)
                await _quiet(judge, o)
            fired = len(FAILS) > before
            if fired:
                FAILS[:] = FAILS[:before]          # 反证触发的 FAIL 不计入本闸失败
            expect_fail(name, "判据确实 FAIL", "", fired)
    finally:
        kill_tree(proc)
        clean_profiles()
        static.kill()


async def _quiet(judge, *args):
    """跑判据但把打印压住，只看有没有产生 FAIL。"""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        judge(*args)
    sys.stdout.write(buf.getvalue())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8777")
    ap.add_argument("--counter", action="store_true", help="只跑反证")
    ap.add_argument("--both", action="store_true", help="正跑＋反证")
    a = ap.parse_args()
    if not EDGE:
        print("FAIL: 未找到 Edge")
        return 1
    os.makedirs(OUT, exist_ok=True)
    print("=" * 68)
    print("件3 五段路径骨架验收闸")
    print("=" * 68)
    if not a.counter:
        asyncio.run(run_normal(a.url))
    if a.counter or a.both:
        asyncio.run(run_counter())
    print("\n" + "=" * 68)
    if SKIPS:
        print(f"跳过的反证（锚文本不在页面）：{SKIPS}——须同步本脚本")
    if FAILS:
        print(f"[FAIL] 五段骨架闸 {len(FAILS)} 项未过：")
        for f in FAILS:
            print("   - " + f)
        return 1
    # 此处禁写 emoji：GBK 控制台下 print 直接 UnicodeEncodeError、traceback 退出，
    # 判据全过也会被外层读成 rc≠0（与"收口检查第4门编码假阴性"同族病灶）。
    print("[PASS] 五段骨架闸全通过" + ("（含反证有牙）" if a.counter or a.both else
          "（本轮未跑反证，须 --both 才算验到有牙）"))
    print("\n仍不可替代的项（如实标注）：")
    print("   ① 真机 WebXR 会话结束／头显内退出手势——须法师在场（金口#7）")
    print("   ② 声音一项在本场景结构上 N/A（源码级禁音视频），S4 接入后须实测＋听感")
    print("   ③ 变化段载体：linewidth 恒 1px 实测已封死甲案前提；张力层（判据 9/10）为第四条候选，真机体感候法师（设计稿 20261012_W1 §九）")
    print("   ④ 五段体感观察问题（D 级）——任何脚本无法替代")
    return 0


if __name__ == "__main__":
    sys.exit(main())
